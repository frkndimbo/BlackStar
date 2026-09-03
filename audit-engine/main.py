import argparse
import logging
import sys
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table

from config import config
from fetcher.contest_fetcher import ContestFetcher, ContestTarget
from analyzers.static_engine import StaticEngine
from llm_core.semantic_auditor import SemanticAuditor, VerifiedVulnerability
from poc_generator.forge_validator import ForgePoCValidator
from reporter.report_builder import ReportBuilder

from telegram_bot.telegram_controller import TelegramController

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("AuditEngineRunner")


class AuditEngineOrchestrator:
    def __init__(self):
        self.fetcher = ContestFetcher()
        self.static_engine = StaticEngine()
        self.semantic_auditor = SemanticAuditor()
        self.poc_validator = ForgePoCValidator()
        self.reporter = ReportBuilder()
        self.telegram_bot = TelegramController(orchestrator=self)

    def audit_target(self, target: ContestTarget) -> Optional[Path]:
        console.rule(f"[bold cyan]Auditing Target: {target.platform} / {target.name}[/bold cyan]")
        
        # 1. Clone & Build
        local_path = self.fetcher.clone_and_prepare(target)
        if not local_path or not local_path.exists():
            logger.error(f"Failed to prepare target {target.name}")
            return None

        # 2. Static Analysis
        console.print(f"[yellow]⚡ Running Aderyn and Slither static scanners on {target.name}...[/yellow]")
        static_findings = self.static_engine.analyze(local_path)
        console.print(f"[green]✓ Static scan completed ({len(static_findings)} High/Medium signals)[/green]")

        # 3. Extract Contracts
        contracts = self.semantic_auditor.extract_key_contracts(local_path)
        console.print(f"[cyan]📁 Found {len(contracts)} core contracts in scope[/cyan]")

        # 4. Semantic Verification & False Positive Pruning
        console.print(f"[yellow]🧠 Performing Semantic Verification & False Positive Filtering...[/yellow]")
        verified_vulns = self.semantic_auditor.verify_and_filter_findings(local_path, static_findings, contracts)
        console.print(f"[green]✓ Verified {len(verified_vulns)} genuine vulnerability candidates[/green]")

        # 5. Deep Cross-Contract Logic Audit (Gemini / OpenAI)
        deep_vulns = self.semantic_auditor.deep_semantic_logic_audit(local_path)
        if deep_vulns:
            console.print(f"[bold green]✨ Discovered {len(deep_vulns)} deep invariant/logic vulnerabilities![/bold green]")
            verified_vulns.extend(deep_vulns)

        # 6. Automated Foundry PoC Validation
        if config.auto_poc_test and verified_vulns:
            console.print(f"[yellow]🧪 Executing automated Foundry PoC validation...[/yellow]")
            validated_list = []
            for vuln in verified_vulns:
                v = self.poc_validator.validate_vulnerability(local_path, vuln)
                validated_list.append(v)
            verified_vulns = validated_list

        # 7. Generate Submission-Ready Report
        report_path = self.reporter.generate_markdown_report(
            platform=target.platform,
            repo_name=target.name,
            vulnerabilities=verified_vulns
        )

        console.print(f"[bold green]✨ Report generated: {report_path.name}[/bold green]\n")
        self.fetcher.mark_completed(f"{target.platform.lower()}_{target.name.lower()}")
        return report_path

    def run_daemon(self):
        console.print("[bold green]🚀 Autonomous 24/7 Web3 Audit Engine started![/bold green]")
        console.print(f"[dim]Polling interval: {config.poll_interval_seconds}s. Target platforms: Code4rena, Sherlock, Cantina.[/dim]\n")

        # Start interactive Telegram controller in background thread
        if config.telegram_bot_token:
            self.telegram_bot.start_polling(background=True)

        # Send Telegram notification on start
        if config.telegram_bot_token and config.telegram_chat_id:
            startup_msg = (
                "🟢 *Web3 Audit Engine is NOW ACTIVE (24/7 Mode)*\n\n"
                f"⏱️ *Interval:* Every {config.poll_interval_seconds // 60} minutes\n"
                "🎯 *Platforms:* Code4rena, Sherlock, Cantina, Immunefi\n"
                "🤖 *Interactive Controller:* Online (Type `/help` for commands)\n"
                "💻 *Status:* Laptop background daemon running..."
            )
            self.telegram_bot.send_message(startup_msg)

        while True:
            try:
                if self.telegram_bot.is_paused:
                    console.print(f"[{time.strftime('%H:%M:%S')}] ⏸️ Daemon is paused via Telegram. Waiting...")
                    time.sleep(10)
                    continue

                targets = self.fetcher.fetch_all_active_contests()
                if not targets:
                    console.print(f"[{time.strftime('%H:%M:%S')}] No new un-scanned contest targets found. Waiting...")
                else:
                    console.print(f"[{time.strftime('%H:%M:%S')}] Found {len(targets)} new targets to audit!")
                    for target in targets:
                        if self.telegram_bot.is_paused:
                            break
                        self.audit_target(target)

            except Exception as e:
                logger.error(f"Error in daemon loop: {e}")

            time.sleep(config.poll_interval_seconds)

    def list_reports(self):
        reports = list(config.reports_dir.glob("*.md"))
        table = Table(title="Generated Audit Reports")
        table.add_column("Report Filename", style="cyan")
        table.add_column("Size", style="magenta")
        table.add_column("Modified Date", style="green")

        for r in sorted(reports, key=lambda x: x.stat().st_mtime, reverse=True):
            table.add_row(r.name, f"{r.stat().st_size} bytes", time.ctime(r.stat().st_mtime))

        console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Autonomous Web3 Smart Contract Audit Engine")
    parser.add_argument("--daemon", action="store_true", help="Run in continuous 24/7 background mode")
    parser.add_argument("--bot", action="store_true", help="Run standalone Telegram Bot interactive controller")
    parser.add_argument("--scan-local", type=str, help="Scan a local folder or cloned repo directly")
    parser.add_argument("--list-reports", action="store_true", help="List all generated audit reports")
    parser.add_argument("--check-tools", action="store_true", help="Check status of all security tools")

    args = parser.parse_args()
    orchestrator = AuditEngineOrchestrator()

    if args.check_tools:
        console.print("[bold cyan]Toolchain Health Check:[/bold cyan]")
        console.print(f"- Forge (Foundry): [green]{config.forge_path}[/green]")
        console.print(f"- Aderyn: [green]{config.aderyn_path}[/green]")
        console.print(f"- Slither: [green]{config.slither_path}[/green]")
        console.print(f"- Solc-Select: [green]{config.solc_select_path}[/green]")
        return

    if args.bot:
        console.print("[bold green]🤖 Starting Standalone Telegram Bot Controller...[/bold green]")
        console.print(f"Connected to bot token ending in ...{config.telegram_bot_token[-6:]}")
        orchestrator.telegram_bot.start_polling(background=False)
        return

    if args.list_reports:
        orchestrator.list_reports()
        return

    if args.scan_local:
        path = Path(args.scan_local).resolve()
        target = ContestTarget(platform="Local", name=path.name, repo_url="", local_path=path)
        orchestrator.audit_target(target)
        return

    if args.daemon:
        orchestrator.run_daemon()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
