import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
import requests
from pydantic import BaseModel

from config import config

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("ContestFetcher")


class ContestTarget(BaseModel):
    platform: str
    name: str
    repo_url: str
    description: Optional[str] = ""
    local_path: Optional[Path] = None
    framework: Optional[str] = "unknown"  # foundry, hardhat, brownie, unknown


class ContestFetcher:
    def __init__(self):
        self.repos_dir = config.repos_dir
        self.cache_file = config.cache_dir / "scanned_contests.json"
        self.scanned_contests = self._load_cache()

    def _load_cache(self) -> set:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                    return set(x.lower() for x in data)
            except Exception as e:
                logger.warning(f"Error loading cache: {e}")
        return set()

    def _save_cache(self):
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(sorted(list(self.scanned_contests)), f, indent=2)

    def fetch_github_org_repos(self, org: str, platform_name: str, limit: int = 5) -> List[ContestTarget]:
        """Fetch latest repos from an organization (Code4rena or Sherlock)."""
        url = f"https://api.github.com/orgs/{org}/repos?sort=created&direction=desc&per_page={limit}"
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Tesseract-Audit-Engine"}
        targets = []

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                repos = resp.json()
                for r in repos:
                    repo_name = r.get("name", "")
                    cache_key = f"{platform_name.lower()}_{repo_name.lower()}"
                    if cache_key in self.scanned_contests:
                        continue

                    # Exclude non-smart-contract repos (judging, docs, findings, profiles, templates)
                    name_lower = repo_name.lower()
                    if any(x in name_lower for x in [
                        "template", "docs", "guide", "profile", ".github",
                        "-judging", "_judging", "-findings", "_findings",
                        "-report", "submissions-tmp"
                    ]):
                        continue

                    targets.append(ContestTarget(
                        platform=platform_name,
                        name=repo_name,
                        repo_url=r.get("clone_url", ""),
                        description=r.get("description", "")
                    ))
            else:
                logger.warning(f"Failed to fetch {org} repos: HTTP {resp.status_code}")
        except Exception as e:
            logger.error(f"Network error fetching {org}: {e}")

        return targets

    def fetch_all_active_contests(self) -> List[ContestTarget]:
        """Fetch newly discovered targets from all configured platforms."""
        targets = []
        # Code4rena
        c4_targets = self.fetch_github_org_repos("code-423n4", "Code4rena", limit=5)
        targets.extend(c4_targets)
        # Sherlock
        sherlock_targets = self.fetch_github_org_repos("sherlock-audit", "Sherlock", limit=5)
        targets.extend(sherlock_targets)
        return targets

    def clone_and_prepare(self, target: ContestTarget) -> Optional[Path]:
        """Clone repository and detect/build framework."""
        if target.local_path and target.local_path.exists():
            target.framework = self._detect_framework(target.local_path)
            self._init_dependencies(target.local_path, target.framework)
            return target.local_path

        dest_dir = self.repos_dir / target.platform.lower() / target.name
        if dest_dir.exists():
            logger.info(f"Target {target.name} already exists locally at {dest_dir}")
            target.local_path = dest_dir
            target.framework = self._detect_framework(dest_dir)
            self._init_dependencies(dest_dir, target.framework)
            return dest_dir

        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Cloning {target.repo_url} into {dest_dir}...")
        
        try:
            res = subprocess.run(
                ["git", "clone", "--depth", "1", "--recurse-submodules", target.repo_url, str(dest_dir)],
                capture_output=True,
                text=True,
                timeout=120
            )
            if res.returncode != 0:
                logger.error(f"Git clone failed: {res.stderr}")
                return None

            target.local_path = dest_dir
            target.framework = self._detect_framework(dest_dir)
            self._init_dependencies(dest_dir, target.framework)
            return dest_dir
        except Exception as e:
            logger.error(f"Failed to clone {target.name}: {e}")
            return None

    def _detect_framework(self, path: Path) -> str:
        if (path / "foundry.toml").exists():
            return "foundry"
        if (path / "hardhat.config.js").exists() or (path / "hardhat.config.ts").exists():
            return "hardhat"
        if (path / "truffle-config.js").exists():
            return "truffle"
        return "unknown"

    def _init_dependencies(self, path: Path, framework: str):
        """Run package manager install, submodules, and solc setup if needed."""
        try:
            # 1. Update submodules
            subprocess.run(["git", "submodule", "update", "--init", "--recursive"], cwd=path, capture_output=True, timeout=60)
            
            # 2. Framework-specific install
            if framework == "foundry":
                logger.info(f"Running forge install in {path}")
                subprocess.run([config.forge_path, "install"], cwd=path, capture_output=True, timeout=60)
            if (path / "package.json").exists():
                logger.info(f"Running npm install in {path}")
                subprocess.run(["npm", "install", "--prefer-offline", "--no-audit"], cwd=path, capture_output=True, timeout=120)

            # 3. Solc version detection
            self._auto_select_solc(path)
        except Exception as e:
            logger.warning(f"Dependency setup warning: {e}")

    def _auto_select_solc(self, path: Path):
        """Detect solidity version pragma and configure solc-select."""
        try:
            sol_files = list(path.glob("**/*.sol"))[:10]
            for sf in sol_files:
                with open(sf, "r", errors="ignore") as f:
                    content = f.read(1000)
                    import re
                    m = re.search(r"pragma\s+solidity\s+[\^>=<]*\s*([0-9]+\.[0-9]+\.[0-9]+)", content)
                    if m:
                        ver = m.group(1)
                        logger.info(f"Detected Solidity pragma {ver}, configuring solc-select...")
                        subprocess.run([config.solc_select_path, "use", ver], capture_output=True, timeout=15)
                        break
        except Exception as e:
            logger.debug(f"Solc-select auto setup skipped: {e}")

    def mark_completed(self, target_id: str):
        self.scanned_contests.add(target_id.lower())
        self._save_cache()
