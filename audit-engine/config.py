import os
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

STORAGE_DIR = BASE_DIR / "storage"
REPOS_DIR = STORAGE_DIR / "repos"
REPORTS_DIR = STORAGE_DIR / "reports"
CACHE_DIR = STORAGE_DIR / "cache"

HOME = Path.home()
FOUNDRY_BIN = HOME / ".foundry" / "bin" / "forge"
ADERYN_BIN = HOME / ".cargo" / "bin" / "aderyn"
VENV_BIN = BASE_DIR.parent / ".venv" / "bin"
SLITHER_BIN = VENV_BIN / "slither"
SOLC_SELECT_BIN = VENV_BIN / "solc-select"


class EngineConfig(BaseModel):
    # Paths
    base_dir: Path = BASE_DIR
    repos_dir: Path = REPOS_DIR
    reports_dir: Path = REPORTS_DIR
    cache_dir: Path = CACHE_DIR

    # Binaries
    forge_path: str = str(FOUNDRY_BIN) if FOUNDRY_BIN.exists() else "forge"
    aderyn_path: str = str(ADERYN_BIN) if ADERYN_BIN.exists() else "aderyn"
    slither_path: str = str(SLITHER_BIN) if SLITHER_BIN.exists() else "slither"
    solc_select_path: str = str(SOLC_SELECT_BIN) if SOLC_SELECT_BIN.exists() else "solc-select"

    # Notification Webhooks (Optional)
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")

    # LLM Engine Configuration
    gemini_api_key: str = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    gemini_model_flash: str = os.getenv("GEMINI_MODEL_FLASH", "gemini-2.5-flash")
    gemini_model_pro: str = os.getenv("GEMINI_MODEL_PRO", "gemini-2.5-pro")
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")

    # Runner parameters
    poll_interval_seconds: int = 3600  # Poll every 1 hour in daemon mode
    min_severity_report: str = "Medium"  # Low, Medium, High
    auto_poc_test: bool = True
    max_contracts_per_contest: int = 25


config = EngineConfig()
