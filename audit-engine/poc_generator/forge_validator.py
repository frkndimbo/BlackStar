import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple
from config import config

logger = logging.getLogger("ForgePoCValidator")


class ForgePoCValidator:
    def __init__(self):
        self.forge_bin = config.forge_path

    def run_poc_test(self, repo_path: Path, poc_code: str, test_name: str = "ExploitPoC") -> Tuple[bool, str]:
        """
        Injects a Foundry test contract, runs `forge test`, and checks if exploit passes.
        Returns: (is_successful, execution_output_logs)
        """
        test_dir = repo_path / "test"
        if not test_dir.exists():
            test_dir = repo_path / "tests"
        test_dir.mkdir(parents=True, exist_ok=True)

        poc_file = test_dir / f"{test_name}.t.sol"

        try:
            with open(poc_file, "w", encoding="utf-8") as f:
                f.write(poc_code)

            logger.info(f"Executing Foundry PoC test: {poc_file.name} in {repo_path.name}...")
            cmd = [
                self.forge_bin,
                "test",
                "--match-path",
                str(poc_file),
                "-vvv"
            ]

            res = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            output = res.stdout + "\n" + res.stderr
            is_pass = "[PASS]" in output and res.returncode == 0

            if is_pass:
                logger.info(f"✅ PoC validation PASSED for {test_name}!")
            else:
                logger.info(f"❌ PoC did not pass for {test_name}. Output summary: {output[:300]}...")

            return is_pass, output
        except Exception as e:
            logger.error(f"Error running Foundry PoC: {e}")
            return False, str(e)
        finally:
            # Preserve or clean up PoC file
            if poc_file.exists():
                poc_file.unlink(missing_ok=True)

    def validate_vulnerability(self, repo_path: Path, vuln: Any) -> Any:
        """Executes PoC if solidity code exists and annotates verification status."""
        if not vuln.poc_solidity_code or len(vuln.poc_solidity_code.strip()) < 50:
            return vuln

        clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", vuln.contract_name or "Exploit")
        test_name = f"AuditPoC_{clean_name}_{vuln.severity}"
        
        is_pass, output = self.run_poc_test(repo_path, vuln.poc_solidity_code, test_name=test_name)
        vuln.is_poc_verified = is_pass
        if is_pass:
            vuln.impact_summary += f"\n\n**Foundry Test Evidence:**\n```text\n{output[:500]}\n```"
        return vuln

    def generate_foundry_template(self, target_contract: str, target_import_path: str) -> str:
        """Helper template for creating standard Foundry exploit tests."""
        return f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "{target_import_path}";

contract ExploitPoCTest is Test {{
    {target_contract} public target;
    address public attacker = makeAddr("attacker");
    address public victim = makeAddr("victim");

    function setUp() public {{
        // Setup initial balances and deployments
        vm.deal(attacker, 10 ether);
        vm.deal(victim, 100 ether);
    }}

    function test_exploit() public {{
        vm.startPrank(attacker);
        // Exploit logic simulation
        vm.stopPrank();

        // Assert economic invariant breakage or unauthorized drain
        // assertTrue(...);
    }}
}}
"""
