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
    auto_scan_interval_minutes: int = _int("AUTO_SCAN_INTERVAL_MINUTES", 15)
    auto_alert_min_score: float = _float("AUTO_ALERT_MIN_SCORE", 60)
    auto_duplicate_cooldown_minutes: int = _int("AUTO_DUPLICATE_COOLDOWN_MINUTES", 180)
    auto_timezone: str = os.getenv("AUTO_TIMEZONE", "Australia/Brisbane")
    auto_peak_start_hour: int = _int("AUTO_PEAK_START_HOUR", 18)
    auto_peak_end_hour: int = _int("AUTO_PEAK_END_HOUR", 2)
    wallet_check_interval_seconds: int = _int("WALLET_CHECK_INTERVAL_SECONDS", 60)
