import os
import sys
import time
import requests
from pathlib import Path
from rich.console import Console

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

console = Console()


def update_env_file(key: str, value: str):
    lines = []
    if ENV_FILE.exists():
        with open(ENV_FILE, "r") as f:
            lines = f.readlines()

    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"{key}={value}\n")

    with open(ENV_FILE, "w") as f:
        f.writelines(new_lines)


def main():
    console.print("[bold cyan]🤖 Telegram Bot Configuration Setup[/bold cyan]\n")

    # Read current token from env file or environment
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "8619142325:AAExFmTj-K0VW9RyCqsEcuwQV40EBuhjZp8")

    # 1. Verify Bot Token
    try:
        resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10).json()
        if not resp.get("ok"):
            console.print(f"[bold red]❌ Token bot tidak valid:[/bold red] {resp.get('description')}")
            return
        bot_info = resp["result"]
        bot_username = bot_info.get("username")
        bot_name = bot_info.get("first_name")
        console.print(f"[green]✓ Terhubung ke Bot:[/green] [bold]{bot_name}[/bold] (@{bot_username})")
    except Exception as e:
        console.print(f"[bold red]❌ Gagal menghubungi Telegram API:[/bold red] {e}")
        return

    update_env_file("TELEGRAM_BOT_TOKEN", bot_token)

    # 2. Check for Chat ID
    console.print(f"\n[yellow]👉 Silakan buka Telegram di HP/Laptop Anda dan kirim pesan apa saja (misal: /start atau 'halo')[/yellow]")
    console.print(f"[yellow]   ke bot Anda: [bold cyan]https://t.me/{bot_username}[/bold cyan][/yellow]\n")
    console.print("Menunggu pesan dari Anda untuk mendeteksi Chat ID (tekan Ctrl+C untuk batal)...")

    detected_chat_id = None
    max_retries = 30  # Wait up to 60 seconds
    for attempt in range(max_retries):
        try:
            updates = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates", timeout=5).json()
            if updates.get("ok") and updates.get("result"):
                # Grab latest message
                latest_msg = updates["result"][-1]
                message_obj = latest_msg.get("message") or latest_msg.get("channel_post") or latest_msg.get("my_chat_member", {}).get("chat")
                if message_obj and "chat" in message_obj:
                    detected_chat_id = str(message_obj["chat"]["id"])
                    user_name = message_obj.get("from", {}).get("first_name", "User")
                    console.print(f"\n[bold green]✓ Pesan terdeteksi dari {user_name}! Chat ID: {detected_chat_id}[/bold green]")
                    break
                elif "id" in message_obj:
                    detected_chat_id = str(message_obj["id"])
                    console.print(f"\n[bold green]✓ Chat terdeteksi! Chat ID: {detected_chat_id}[/bold green]")
                    break
        except Exception as e:
            pass

        time.sleep(2)
        print(".", end="", flush=True)

    if not detected_chat_id:
        console.print("\n[red]Waktu habis. Pastikan Anda sudah menekan 'START' atau mengirim pesan ke bot, lalu jalankan kembali skrip ini.[/red]")
        return

    # 3. Save Chat ID
    update_env_file("TELEGRAM_CHAT_ID", detected_chat_id)
    console.print(f"[green]✓ Chat ID tersimpan di `.env`[/green]")

    # 4. Send Test Message
    test_msg = (
        "🎉 *Web3 Smart Contract Audit Engine*\n\n"
        "✅ Notifikasi Telegram telah berhasil terhubung!\n"
        "Engine ini akan otomatis mengirimkan laporan saat menemukan celah keamanan (High/Medium) pada kontes Cantina / Immunefi."
    )
    try:
        send_resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": detected_chat_id, "text": test_msg, "parse_mode": "Markdown"},
            timeout=10
        ).json()
        if send_resp.get("ok"):
            console.print(f"[bold green]🚀 Pesan uji coba berhasil dikirim ke Telegram Anda![/bold green]\n")
        else:
            console.print(f"[yellow]Peringatan saat kirim pesan test: {send_resp.get('description')}[/yellow]")
    except Exception as e:
        console.print(f"[red]Gagal mengirim pesan test: {e}[/red]")


if __name__ == "__main__":
    main()
