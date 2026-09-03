import datetime
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
import requests

from config import config

logger = logging.getLogger("TelegramController")


class TelegramController:
    def __init__(self, orchestrator: Any = None):
        self.bot_token = config.telegram_bot_token
        self.admin_chat_id = str(config.telegram_chat_id)
        self.orchestrator = orchestrator
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.is_running = False
        self.poll_thread: Optional[threading.Thread] = None
        self.is_paused = False
        self.last_update_id = 0
        self.start_time = time.time()

    def is_authorized(self, chat_id: Any) -> bool:
        """Verify that the sender is the configured admin chat ID."""
        if not self.admin_chat_id:
            return True
        return str(chat_id) == str(self.admin_chat_id)

    def send_message(self, text: str, chat_id: Optional[str] = None, parse_mode: str = "Markdown") -> bool:
        """Sends a text message to Telegram."""
        target_chat = chat_id or self.admin_chat_id
        if not self.bot_token or not target_chat:
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if not data.get("ok"):
                # Fallback without markdown parsing if syntax error
                payload["parse_mode"] = ""
                requests.post(url, json=payload, timeout=10)
            return True
        except Exception as e:
            logger.warning(f"Failed to send Telegram message: {e}")
            return False

    def send_document(self, file_path: Path, caption: str = "", chat_id: Optional[str] = None) -> bool:
        """Uploads and sends a file (e.g. .md report) to Telegram."""
        target_chat = chat_id or self.admin_chat_id
        if not self.bot_token or not target_chat or not file_path.exists():
            return False

        url = f"{self.base_url}/sendDocument"
        try:
            with open(file_path, "rb") as f:
                data = {"chat_id": target_chat, "caption": caption}
                files = {"document": f}
                resp = requests.post(url, data=data, files=files, timeout=30)
                data_resp = resp.json()
                return data_resp.get("ok", False)
        except Exception as e:
            logger.warning(f"Failed to upload document {file_path.name} to Telegram: {e}")
            return False

    def handle_command(self, text: str, chat_id: str):
        """Dispatches incoming Telegram bot commands."""
        parts = text.strip().split()
        if not parts:
            return

        raw_cmd = parts[0].split("@")[0].lower()
        args = parts[1:]

        logger.info(f"Received Telegram command: {raw_cmd} with args: {args} from chat {chat_id}")

        if raw_cmd in ["/start", "/help"]:
            self._cmd_help(chat_id)
        elif raw_cmd == "/status":
            self._cmd_status(chat_id)
        elif raw_cmd == "/tools":
            self._cmd_tools(chat_id)
        elif raw_cmd == "/reports":
            self._cmd_reports(chat_id)
        elif raw_cmd == "/getreport":
            self._cmd_getreport(chat_id, args)
        elif raw_cmd == "/scan":
            self._cmd_scan(chat_id, args)
        elif raw_cmd == "/pause":
            self._cmd_pause(chat_id)
        elif raw_cmd == "/resume":
            self._cmd_resume(chat_id)
        elif raw_cmd == "/findings":
            self._cmd_findings(chat_id)
        else:
            self.send_message("❓ Perintah tidak dikenali. Ketik /help untuk melihat daftar perintah yang tersedia.", chat_id)

    def _cmd_help(self, chat_id: str):
        msg = (
            "🛡️ *Autonomous Web3 Audit Engine Controller*\n\n"
            "*Daftar Perintah Tersedia:*\n"
            "• `/status` - Cek status daemon & statistik pemindaian\n"
            "• `/tools` - Health check toolchain (Aderyn, Slither, Forge, LLM)\n"
            "• `/scan <repo_url / nama>` - Mulai audit on-demand langsung\n"
            "• `/reports` - Daftar 10 laporan hasil audit terbaru\n"
            "• `/getreport <nama_file / index>` - Unduh file laporan .md\n"
            "• `/findings` - Ringkasan temuan celah keamanan aktif\n"
            "• `/pause` - Jeda siklus polling daemon 24/7\n"
            "• `/resume` - Lanjutkan siklus polling daemon\n"
            "• `/help` - Menampilkan panduan bantuan ini"
        )
        self.send_message(msg, chat_id)

    def _cmd_status(self, chat_id: str):
        uptime_sec = int(time.time() - self.start_time)
        hours, rem = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{hours}j {minutes}m {seconds}s"

        reports_count = len(list(config.reports_dir.glob("*.md")))
        cache_count = 0
        if self.orchestrator and hasattr(self.orchestrator, "fetcher"):
            cache_count = len(self.orchestrator.fetcher.scanned_contests)

        mode_str = "⏸️ Dijeda (/resume untuk lanjut)" if self.is_paused else "🟢 Aktif (Memantau 24/7)"
        
        msg = (
            "📊 *Audit Engine Status Overview*\n\n"
            f"• *Status Daemon:* {mode_str}\n"
            f"• *Uptime:* `{uptime_str}`\n"
            f"• *Laporan Tersedia:* `{reports_count} file`\n"
            f"• *Target Selesai di-Cache:* `{cache_count} repos`\n"
            f"• *Interval Polling:* `{config.poll_interval_seconds // 60} menit`\n"
            f"• *LLM Engine:* `Gemini 2.5 Flash / Pro`"
        )
        self.send_message(msg, chat_id)

    def _cmd_tools(self, chat_id: str):
        forge_ok = "✅ Ready" if Path(config.forge_path).exists() or config.forge_path == "forge" else "❌ Missing"
        aderyn_ok = "✅ Ready" if Path(config.aderyn_path).exists() or config.aderyn_path == "aderyn" else "❌ Missing"
        slither_ok = "✅ Ready" if Path(config.slither_path).exists() or config.slither_path == "slither" else "❌ Missing"
        solc_ok = "✅ Ready" if Path(config.solc_select_path).exists() or config.solc_select_path == "solc-select" else "❌ Missing"
        
        llm_status = "✅ Configured" if (config.gemini_api_key or config.openai_api_key) else "⚠️ Heuristic Fallback (No Key)"

        msg = (
            "🛠️ *Toolchain Health Check:*\n\n"
            f"• *Foundry (Forge):* {forge_ok}\n"
            f"• *Cyfrin Aderyn:* {aderyn_ok}\n"
            f"• *Trail of Bits Slither:* {slither_ok}\n"
            f"• *Solc-Select:* {solc_ok}\n"
            f"• *LLM Semantic Verifier:* {llm_status}\n"
            f"• *PoC Auto-Validator:* {'✅ Enabled' if config.auto_poc_test else '❌ Disabled'}"
        )
        self.send_message(msg, chat_id)

    def _cmd_reports(self, chat_id: str):
        reports = sorted(list(config.reports_dir.glob("*.md")), key=lambda x: x.stat().st_mtime, reverse=True)
        if not reports:
            self.send_message("📁 Belum ada laporan audit baru di `storage/reports/`.", chat_id)
            return

        lines = ["📂 *Daftar Laporan Audit Terbaru:*\n"]
        for idx, r in enumerate(reports[:10], 1):
            size_kb = round(r.stat().st_size / 1024, 1)
            mod_time = datetime.datetime.fromtimestamp(r.stat().st_mtime).strftime("%d/%m %H:%M")
            lines.append(f"{idx}. `{r.name}` ({size_kb} KB, {mod_time})")

        lines.append("\n💡 *Unduh laporan dengan mengetik:* `/getreport <nomor / nama_file>`")
        self.send_message("\n".join(lines), chat_id)

    def _cmd_getreport(self, chat_id: str, args: List[str]):
        if not args:
            self.send_message("⚠️ Harap sertakan nama file atau nomor index laporan. Contoh: `/getreport 1` atau `/getreport local_2026-04-monetrix`", chat_id)
            return

        reports = sorted(list(config.reports_dir.glob("*.md")), key=lambda x: x.stat().st_mtime, reverse=True)
        query = args[0].strip()

        target_file: Optional[Path] = None
        if query.isdigit():
            idx = int(query) - 1
            if 0 <= idx < len(reports):
                target_file = reports[idx]
        else:
            for r in reports:
                if query.lower() in r.name.lower():
                    target_file = r
                    break

        if not target_file:
            self.send_message(f"❌ Laporan dengan kata kunci `{query}` tidak ditemukan.", chat_id)
            return

        self.send_message(f"📤 Mengirimkan laporan `{target_file.name}`...", chat_id)
        ok = self.send_document(target_file, caption=f"📄 Laporan Audit: `{target_file.name}`", chat_id=chat_id)
        if not ok:
            self.send_message(f"❌ Gagal mengirim dokumen `{target_file.name}`.", chat_id)

    def _cmd_scan(self, chat_id: str, args: List[str]):
        if not args:
            self.send_message("⚠️ Harap tentukan nama target atau URL repo yang ingin di-scan.\nContoh: `/scan monetrix` atau `/scan https://github.com/code-423n4/2026-04-monetrix`", chat_id)
            return

        target_str = args[0].strip()
        self.send_message(f"🚀 *Memulai On-Demand Audit untuk:* `{target_str}`...\nProses akan berjalan di background.", chat_id)

        def _run_scan_thread():
            try:
                from fetcher.contest_fetcher import ContestTarget
                # 1. Check if local directory matches
                local_repo = None
                for sub in (config.repos_dir / "code4rena", config.repos_dir / "sherlock", config.repos_dir / "local"):
                    if sub.exists():
                        for p in sub.iterdir():
                            if target_str.lower() in p.name.lower():
                                local_repo = p
                                break
                    if local_repo:
                        break

                if local_repo:
                    t = ContestTarget(platform="Local", name=local_repo.name, repo_url="", local_path=local_repo)
                elif target_str.startswith("http"):
                    repo_name = target_str.rstrip("/").split("/")[-1]
                    t = ContestTarget(platform="OnDemand", name=repo_name, repo_url=target_str)
                else:
                    self.send_message(f"❌ Target `{target_str}` tidak ditemukan di lokal dan bukan URL valid.", chat_id)
                    return

                if not self.orchestrator:
                    from main import AuditEngineOrchestrator
                    self.orchestrator = AuditEngineOrchestrator()

                report_path = self.orchestrator.audit_target(t)
                if report_path and report_path.exists():
                    self.send_message(f"✅ *Audit Selesai:* `{t.name}`!\nFile laporan siap diunduh.", chat_id)
                    self.send_document(report_path, caption=f"✨ Hasil Audit `{t.name}`", chat_id=chat_id)
                else:
                    self.send_message(f"⚠️ Audit `{t.name}` selesai tanpa file laporan yang dihasilkan.", chat_id)
            except Exception as e:
                logger.error(f"Scan thread error: {e}")
                self.send_message(f"❌ Terjadi kesalahan saat audit `{target_str}`: {e}", chat_id)

        threading.Thread(target=_run_scan_thread, daemon=True).start()

    def _cmd_pause(self, chat_id: str):
        self.is_paused = True
        self.send_message("⏸️ *Daemon audit 24/7 telah dijeda.* Kirim `/resume` untuk mengaktifkan kembali.", chat_id)

    def _cmd_resume(self, chat_id: str):
        self.is_paused = False
        self.send_message("▶️ *Daemon audit 24/7 telah diaktifkan kembali.*", chat_id)

    def _cmd_findings(self, chat_id: str):
        reports = list(config.reports_dir.glob("*.md"))
        if not reports:
            self.send_message("Belum ada laporan temuan aktif.", chat_id)
            return

        import re
        total_vulns = []
        for r in reports:
            try:
                with open(r, "r", errors="ignore") as f:
                    content = f.read()
                matches = re.findall(r"## (\[(?:H|M)-\d+\] .*?)\n- \*\*Severity:\*\* (.*?)\n- \*\*Target Contract:\*\* `(.*?)`", content)
                for title, sev, contract in matches:
                    total_vulns.append((r.name, sev, title, contract))
            except Exception:
                pass

        if not total_vulns:
            self.send_message("🛡️ *Tidak ada temuan High / Medium aktif pada laporan saat ini.*", chat_id)
            return

        lines = [f"🚨 *Total Temuan Terverifikasi:* `{len(total_vulns)} Temuan`\n"]
        for rname, sev, title, contract in total_vulns[:10]:
            icon = "🔴" if "high" in sev.lower() else "🟡"
            lines.append(f"{icon} *{sev}:* {title}\n   └ *Target:* `{contract}` ({rname})")

        self.send_message("\n".join(lines), chat_id)

    def poll_updates(self):
        """Long-polling worker thread for real-time Telegram interaction."""
        logger.info("Telegram long-polling listener started...")
        while self.is_running:
            try:
                url = f"{self.base_url}/getUpdates?offset={self.last_update_id + 1}&timeout=20"
                resp = requests.get(url, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        self.last_update_id = update.get("update_id", self.last_update_id)
                        msg = update.get("message")
                        if msg and "text" in msg:
                            chat_id = str(msg.get("chat", {}).get("id"))
                            text = msg.get("text", "")
                            if self.is_authorized(chat_id):
                                self.handle_command(text, chat_id)
                            else:
                                logger.warning(f"Unauthorized Telegram access attempt from Chat ID: {chat_id}")
                                self.send_message("⛔ Akses ditolak. Chat ID Anda tidak terdaftar sebagai administrator.", chat_id)
            except requests.exceptions.Timeout:
                pass
            except Exception as e:
                logger.debug(f"Telegram polling loop exception: {e}")
                time.sleep(3)

    def start_polling(self, background: bool = True):
        """Starts the Telegram controller polling service."""
        if self.is_running:
            return

        self.is_running = True
        if background:
            self.poll_thread = threading.Thread(target=self.poll_updates, daemon=True)
            self.poll_thread.start()
            logger.info("Telegram Bot controller running in background thread.")
        else:
            self.poll_updates()

    def stop_polling(self):
        """Stops the Telegram controller polling service."""
        self.is_running = False
        if self.poll_thread and self.poll_thread.is_alive():
            self.poll_thread.join(timeout=2)
