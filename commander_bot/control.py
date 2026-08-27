from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
        auto_detail = ""
        if mode == "AUTOMATIC":
            auto_detail = (
                f"\nPeak window: {self.settings.auto_peak_start_hour:02d}:00–"
                f"{self.settings.auto_peak_end_hour:02d}:00 ({self.settings.auto_timezone})"
                f"\nScan interval: {self.settings.auto_scan_interval_minutes} minutes"
                f"\nAlert score floor: {self.settings.auto_alert_min_score:.0f}/100"
                f"\nLast auto result: {self.ledger.get_state('last_auto_result', 'Waiting for peak window')}"
            )
        return (
            f"🛰️ DEGEN DETECTOR STATUS\n"
            f"Mode: {mode}\n"
            f"Trading: PAPER ONLY\n"
            f"Wallet access: DISABLED{detail}{auto_detail}"
        )

    def handle(self, action: str) -> str:
        if action not in VALID_ACTIONS:
            return "Unknown command."
        if action == "scan_once":
            if self.mode == "EMERGENCY_STOP":
                return "🚨 Scan blocked: Emergency Stop is enabled."
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
            self.ledger.set_state("next_auto_scan", "")
            return (
                "🕒 Automatic mode enabled. Paper-only scans will run during the configured "
                "peak window; repeat and low-score alerts are suppressed."
            )
        self.ledger.set_state("mode", "EMERGENCY_STOP" if action == "emergency_stop" else "OFF")
        self.ledger.set_state("manual_until", "")
        return "🚨 Emergency stop enabled. All scanning is blocked." if action == "emergency_stop" else "⏹️ Scanning stopped."

    def _inside_peak_window(self, now: datetime) -> bool:
        try:
            local_hour = now.astimezone(ZoneInfo(self.settings.auto_timezone)).hour
        except ZoneInfoNotFoundError:
            local_hour = now.astimezone(timezone.utc).hour
        start = self.settings.auto_peak_start_hour % 24
        end = self.settings.auto_peak_end_hour % 24
        if start == end:
            return True
        return start <= local_hour < end if start < end else local_hour >= start or local_hour < end

    def maybe_run_automatic(self, now: Optional[datetime] = None) -> Optional[str]:
        now = now or datetime.now(timezone.utc)
        if self.mode != "AUTOMATIC" or not self._inside_peak_window(now):
            return None
        due_text = self.ledger.get_state("next_auto_scan", "")
        if due_text and now < datetime.fromisoformat(due_text):
            return None
        next_scan = now + timedelta(minutes=max(1, self.settings.auto_scan_interval_minutes))
        self.ledger.set_state("next_auto_scan", next_scan.isoformat())
        try:
            from .live_data import run_automatic_scan
            result = run_automatic_scan(self.settings, now)
        except (OSError, RuntimeError, ValueError) as error:
            result = f"Automatic scan error: {type(error).__name__}"
        self.ledger.set_state("last_auto_result", result)
        return result


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
        controller.maybe_run_automatic()
