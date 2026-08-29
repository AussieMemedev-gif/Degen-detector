import re
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


def parse_telegram_ids(value: str) -> frozenset[str]:
    """Parse a comma/space-separated allowlist without accepting arbitrary text."""
    return frozenset(re.findall(r"-?\d+", value or ""))


@dataclass(frozen=True)
class TelegramAccess:
    owner_id: str
    tester_ids: frozenset[str]
    alert_group_id: str = ""

    @classmethod
    def from_settings(cls, settings: Settings) -> "TelegramAccess":
        owner_id = str(settings.telegram_owner_id or settings.telegram_chat_id).strip()
        return cls(
            owner_id=owner_id,
            tester_ids=parse_telegram_ids(settings.telegram_tester_ids) - {owner_id},
            alert_group_id=str(settings.telegram_alert_group_id).strip(),
        )

    def role(self, telegram_user_id: str) -> str:
        user_id = str(telegram_user_id).strip()
        if user_id and user_id == self.owner_id:
            return "owner"
        if user_id and user_id in self.tester_ids:
            return "tester"
        return "unauthorized"


def user_database_path(database_path: str, telegram_user_id: str) -> str:
    """Give each tester isolated tracked wallets, settings and paper positions."""
    if database_path == ":memory:":
        return database_path
    path = Path(database_path)
    safe_id = re.sub(r"\D", "", str(telegram_user_id)) or "unknown"
    suffix = path.suffix or ".db"
    stem = path.stem if path.suffix else path.name
    return str(path.with_name(f"{stem}.user-{safe_id}{suffix}"))
