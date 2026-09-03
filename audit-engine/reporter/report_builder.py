import datetime
import json
import logging
from pathlib import Path
from typing import List, Optional
import requests

from config import config
from llm_core.semantic_auditor import VerifiedVulnerability

logger = logging.getLogger("ReportBuilder")


class ReportBuilder:
    def __init__(self):
        self.reports_dir = config.reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_markdown_report(
        self,
        platform: str,
        repo_name: str,
        vulnerabilities: List[VerifiedVulnerability]
    ) -> Path:
        """Generates submission-ready Markdown report formatted for the target platform."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"{platform.lower()}_{repo_name}_{timestamp}.md"
        report_path = self.reports_dir / report_filename

        content_lines = [
            f"# Security Audit Finding Report: {repo_name}",
            f"- **Platform Target:** {platform}",
            f"- **Audit Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Total High/Medium Findings:** {len(vulnerabilities)}",
            "",
            "---",
            ""
        ]

        if not vulnerabilities:
            content_lines.append("> [!NOTE]\n> No High or Medium severity vulnerabilities detected in this scan.")
        else:
            for idx, vuln in enumerate(vulnerabilities, 1):
                severity_tag = f"[H-{idx:02d}]" if vuln.severity == "High" else f"[M-{idx:02d}]"
                poc_status = "✅ Foundry PoC Verified" if vuln.is_poc_verified else "⚠️ Semantic Analysis"

                content_lines.extend([
                    f"## {severity_tag} {vuln.title}",
                    f"- **Severity:** {vuln.severity}",
                    f"- **Target Contract:** `{vuln.contract_name}` (`{vuln.file_path}`)",
                    f"- **Line Range:** `{vuln.line_range}`",
                    f"- **PoC Status:** {poc_status}",
                    "",
                    "### 1. Impact Summary",
                    vuln.impact_summary,
                    "",
                    "### 2. Vulnerability Detail & Root Cause",
                    vuln.detailed_path,
                    "",
                    "### 3. Step-by-Step Exploit Scenario",
                    vuln.exploit_scenario,
                    "",
                ])

                if vuln.poc_solidity_code:
                    content_lines.extend([
                        "### 4. Proof of Concept (Foundry `.t.sol`)",
                        "```solidity",
                        vuln.poc_solidity_code,
                        "```",
                        ""
                    ])

                content_lines.extend([
                    "### 5. Recommended Mitigation Steps",
                    vuln.recommended_mitigation,
                    "",
                    "---",
                    ""
                ])

        report_text = "\n".join(content_lines)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)

        logger.info(f"Report generated successfully: {report_path}")
        self._send_notification(platform, repo_name, vulnerabilities, report_path)
        return report_path

    def _send_notification(
        self,
        platform: str,
        repo_name: str,
        vulnerabilities: List[VerifiedVulnerability],
        report_path: Path
    ):
        """Sends instant alerts and attaches the .md report to Telegram / Discord if configured."""
        high_count = sum(1 for v in vulnerabilities if v.severity == "High")
        med_count = sum(1 for v in vulnerabilities if v.severity == "Medium")
        poc_count = sum(1 for v in vulnerabilities if v.is_poc_verified)

        status_emoji = "🚨" if high_count > 0 else ("⚠️" if med_count > 0 else "✅")
        msg_lines = [
            f"{status_emoji} *Web3 Smart Contract Audit Alert*",
            f"🎯 *Target:* `{platform} / {repo_name}`",
            f"📊 *Hasil Scan:* 🔴 `{high_count} High`, 🟡 `{med_count} Medium`",
        ]
        if poc_count > 0:
            msg_lines.append(f"🧪 *Foundry PoC Verified:* `{poc_count} Exploit(s)`")
        msg_lines.append(f"📄 *File Laporan:* `{report_path.name}`")

        text_msg = "\n".join(msg_lines)

        # 1. Telegram Message & Document Upload
        if config.telegram_bot_token and config.telegram_chat_id:
            try:
                base_tg = f"https://api.telegram.org/bot{config.telegram_bot_token}"
                # Send summary text
                requests.post(
                    f"{base_tg}/sendMessage",
                    json={"chat_id": config.telegram_chat_id, "text": text_msg, "parse_mode": "Markdown"},
                    timeout=10
                )

                # Send report document (.md)
                if report_path.exists():
                    with open(report_path, "rb") as f:
                        requests.post(
                            f"{base_tg}/sendDocument",
                            data={"chat_id": config.telegram_chat_id, "caption": f"📄 Laporan Audit `{repo_name}`"},
                            files={"document": (report_path.name, f)},
                            timeout=30
                        )
            except Exception as e:
                logger.warning(f"Telegram notification/document upload failed: {e}")

        # 2. Discord Webhook
        if config.discord_webhook_url:
            try:
                requests.post(config.discord_webhook_url, json={"content": text_msg}, timeout=10)
            except Exception as e:
                logger.warning(f"Discord notification failed: {e}")
