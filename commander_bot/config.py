import os
from dataclasses import dataclass


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    bot_display_name: str = os.getenv("BOT_DISPLAY_NAME", "Degen Detector")
    bot_tagline: str = os.getenv("BOT_TAGLINE", "Detect the send before the trend.")
    database_path: str = os.getenv("DATABASE_PATH", "commander_bot.db")
    min_liquidity_usd: float = _float("MIN_LIQUIDITY_USD", 25_000)
    max_top10_holder_pct: float = _float("MAX_TOP10_HOLDER_PCT", 35)
    max_slippage_pct: float = _float("MAX_SLIPPAGE_PCT", 3)
    approval_score: float = _float("COMMANDER_APPROVAL_SCORE", 72)
    paper_position_usd: float = _float("PAPER_POSITION_USD", 25)
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_poll_seconds: int = _int("TELEGRAM_POLL_SECONDS", 20)
    manual_session_minutes: int = _int("MANUAL_SESSION_MINUTES", 60)
    helius_api_key: str = os.getenv("HELIUS_API_KEY", "")
    live_data_enabled: bool = _bool("LIVE_DATA_ENABLED", False)
    live_candidate_limit: int = _int("LIVE_CANDIDATE_LIMIT", 8)
