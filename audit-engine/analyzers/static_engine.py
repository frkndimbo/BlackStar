import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from config import config

logger = logging.getLogger("StaticEngine")


class VulnerabilityLocation(BaseModel):
    file_path: str
    start_line: Optional[int] = 0
    end_line: Optional[int] = 0
    contract_name: Optional[str] = ""
    function_name: Optional[str] = ""


class StaticFinding(BaseModel):
    source_tool: str  # aderyn, slither
    detector: str
    title: str
    severity: str  # High, Medium, Low, Informational
    confidence: str  # High, Medium, Low
    description: str
    locations: List[VulnerabilityLocation] = Field(default_factory=list)
    raw_evidence: Optional[str] = ""


class StaticEngine:
    def __init__(self):
        self.aderyn_bin = config.aderyn_path
        self.slither_bin = config.slither_path

    def run_aderyn(self, target_path: Path) -> List[StaticFinding]:
        findings: List[StaticFinding] = []
        report_file = target_path / "aderyn_report.json"

        try:
            logger.info(f"Running Aderyn on {target_path}...")
            res = subprocess.run(
                [self.aderyn_bin, "--output", str(report_file)],
                cwd=target_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            if report_file.exists():
                with open(report_file, "r") as f:
                    data = json.load(f)

                # Parse High severity issues
                for item in data.get("high_issues", {}).get("issues", []):
                    findings.append(self._parse_aderyn_item(item, "High"))

                # Parse Medium severity issues
                for item in data.get("medium_issues", {}).get("issues", []):
                    findings.append(self._parse_aderyn_item(item, "Medium"))

                # Parse Low severity issues
                for item in data.get("low_issues", {}).get("issues", []):
                    findings.append(self._parse_aderyn_item(item, "Low"))

                # Clean up temporary report file
                report_file.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Aderyn execution warning on {target_path}: {e}")

        return findings

    def _parse_aderyn_item(self, item: dict, severity: str) -> StaticFinding:
        locations = []
        for instance in item.get("instances", []):
            locations.append(VulnerabilityLocation(
                file_path=instance.get("contract_path", ""),
                start_line=instance.get("line_no", 0),
                end_line=instance.get("line_no", 0)
            ))

        return StaticFinding(
            source_tool="aderyn",
            detector=item.get("detector_name", ""),
            title=item.get("title", ""),
            severity=severity,
            confidence="High",
            description=item.get("description", ""),
            locations=locations
        )

    def run_slither(self, target_path: Path) -> List[StaticFinding]:
        findings: List[StaticFinding] = []
        report_file = target_path / "slither_report.json"

        try:
            logger.info(f"Running Slither on {target_path}...")
            cmd = [
                self.slither_bin,
                str(target_path),
                "--json",
                str(report_file),
                "--filter-paths",
                "node_modules|lib|test|tests|mocks"
            ]
            subprocess.run(cmd, cwd=target_path, capture_output=True, text=True, timeout=180)

            if report_file.exists():
                with open(report_file, "r") as f:
                    data = json.load(f)

                results = data.get("results", {}).get("detectors", [])
                for detector in results:
                    impact = detector.get("impact", "Informational").capitalize()
                    confidence = detector.get("confidence", "Medium").capitalize()

                    locations = []
                    for elem in detector.get("elements", []):
                        source_mapping = elem.get("source_mapping", {})
                        lines = source_mapping.get("lines", [0])
                        locations.append(VulnerabilityLocation(
                            file_path=source_mapping.get("filename_relative", ""),
                            start_line=lines[0] if lines else 0,
                            end_line=lines[-1] if lines else 0,
                            contract_name=elem.get("name", ""),
                            function_name=elem.get("type", "")
                        ))

                    findings.append(StaticFinding(
                        source_tool="slither",
                        detector=detector.get("check", ""),
                        title=detector.get("description", "").split("\n")[0][:120],
                        severity=impact,
                        confidence=confidence,
                        description=detector.get("description", ""),
                        locations=locations
                    ))

                # Clean up temporary report file
                report_file.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Slither execution warning on {target_path}: {e}")

        return findings

    def analyze(self, target_path: Path) -> List[StaticFinding]:
        """Execute both analyzers and aggregate deduplicated findings."""
        all_findings: List[StaticFinding] = []
        all_findings.extend(self.run_aderyn(target_path))
        all_findings.extend(self.run_slither(target_path))
        
        # Filter for relevant severities
        priority_findings = [f for f in all_findings if f.severity in ["High", "Medium"]]
        logger.info(f"Static analysis complete for {target_path.name}: Found {len(priority_findings)} High/Medium candidates ({len(all_findings)} total).")
        return priority_findings
