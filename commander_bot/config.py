import os
from dataclasses import dataclass


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


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
