from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import Settings
from .notifications import answer_callback, get_updates, send_control_menu, send_telegram
from .storage import Ledger


VALID_ACTIONS = {"scan_once", "status", "manual_on", "stop", "automatic", "emergency_stop"}


class BotController:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.ledger = Ledger(settings.database_path)
        if not self.ledger.get_state("mode"):
            self.ledger.set_state("mode", "OFF")

    @property
    def mode(self) -> str:
        return self.ledger.get_state("mode", "OFF")

    def status_message(self) -> str:
        mode = self.mode
        expiry = self.ledger.get_state("manual_until", "")
        detail = f"\nManual session ends: {expiry}" if mode == "MANUAL" and expiry else ""
        return (
            f"🛰️ DEGEN DETECTOR STATUS\n"
            f"Mode: {mode}\n"
            f"Trading: PAPER ONLY\n"
            f"Wallet access: DISABLED{detail}"
        )

    def handle(self, action: str) -> str:
        if action not in VALID_ACTIONS:
            return "Unknown command."
        if action == "scan_once":
            from .main import run_once
            run_once(self.settings)
            return "✅ Scan completed. The Commander report has been sent."
        if action == "status":
            return self.status_message()
        if action == "manual_on":
            until = datetime.now(timezone.utc) + timedelta(minutes=self.settings.manual_session_minutes)
            self.ledger.set_state("mode", "MANUAL")
            self.ledger.set_state("manual_until", until.isoformat(timespec="minutes"))
            return f"▶️ Manual mode enabled for {self.settings.manual_session_minutes} minutes."
        if action == "automatic":
            self.ledger.set_state("mode", "AUTOMATIC")
            self.ledger.set_state("manual_until", "")
            return "🕒 Automatic mode selected. Peak-time jobs can now run."
        self.ledger.set_state("mode", "EMERGENCY_STOP" if action == "emergency_stop" else "OFF")
        self.ledger.set_state("manual_until", "")
        return "🚨 Emergency stop enabled. All scanning is blocked." if action == "emergency_stop" else "⏹️ Scanning stopped."


def run_control_bot(settings: Settings) -> None:
    if not settings.telegram_token or not settings.telegram_chat_id:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before starting controls.")
    controller = BotController(settings)
    send_control_menu(settings.telegram_token, settings.telegram_chat_id, "Degen Detector controls are online.")
    offset: Optional[int] = None
    while True:
        for update in get_updates(settings.telegram_token, offset, settings.telegram_poll_seconds):
            offset = update["update_id"] + 1
            callback = update.get("callback_query")
            message = update.get("message")
            if callback:
                chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
                if chat_id != str(settings.telegram_chat_id):
                    answer_callback(settings.telegram_token, callback["id"], "Not authorized")
                    continue
                answer_callback(settings.telegram_token, callback["id"])
                reply = controller.handle(callback.get("data", ""))
                send_control_menu(settings.telegram_token, chat_id, reply)
            elif message and str(message.get("chat", {}).get("id", "")) == str(settings.telegram_chat_id):
                if message.get("text", "").lower() in {"/start", "/menu", "/status"}:
                    send_control_menu(settings.telegram_token, settings.telegram_chat_id, controller.status_message())
