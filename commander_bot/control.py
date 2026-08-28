from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .notifications import answer_callback, get_updates, send_control_menu, send_settings_menu
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

    def _pref_int(self, key: str, default: int) -> int:
        try:
            return int(self.ledger.get_state(key, str(default)))
        except ValueError:
            return default

    def _pref_float(self, key: str, default: float) -> float:
        try:
            return float(self.ledger.get_state(key, str(default)))
        except ValueError:
            return default

    def automatic_settings(self) -> Settings:
        return replace(
            self.settings,
            auto_scan_interval_minutes=max(3, self._pref_int("auto_interval", self.settings.auto_scan_interval_minutes)),
            auto_alert_min_score=max(0, min(100, self._pref_float("auto_score", self.settings.auto_alert_min_score))),
            auto_duplicate_cooldown_minutes=max(0, self._pref_int("auto_cooldown", self.settings.auto_duplicate_cooldown_minutes)),
            auto_peak_start_hour=self._pref_int("auto_peak_start", self.settings.auto_peak_start_hour) % 24,
            auto_peak_end_hour=self._pref_int("auto_peak_end", self.settings.auto_peak_end_hour) % 24,
        )

    def settings_message(self) -> str:
        settings = self.automatic_settings()
        window = "24/7" if settings.auto_peak_start_hour == settings.auto_peak_end_hour else (
            f"{settings.auto_peak_start_hour:02d}:00–{settings.auto_peak_end_hour:02d}:00"
        )
        return (
            "⚙️ DEGEN DETECTOR SETTINGS\n"
            f"Interval: {settings.auto_scan_interval_minutes} minutes\n"
            f"Peak window: {window} ({settings.auto_timezone})\n"
            f"Alert score: {settings.auto_alert_min_score:.0f}/100+\n"
            f"Repeat cooldown: {settings.auto_duplicate_cooldown_minutes} minutes\n\n"
            "Short intervals use more API allowance.\n"
            "Custom: /interval 7, /window 17 3, or /cooldown 120"
        )

    def status_message(self) -> str:
        mode = self.mode
        settings = self.automatic_settings()
        expiry = self.ledger.get_state("manual_until", "")
        detail = f"\nManual session ends: {expiry}" if mode == "MANUAL" and expiry else ""
        auto_detail = ""
        if mode == "AUTOMATIC":
            auto_detail = (
                f"\nPeak window: {settings.auto_peak_start_hour:02d}:00–"
                f"{settings.auto_peak_end_hour:02d}:00 ({settings.auto_timezone})"
                f"\nScan interval: {settings.auto_scan_interval_minutes} minutes"
                f"\nAlert score floor: {settings.auto_alert_min_score:.0f}/100"
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

    def set_preference(self, action: str) -> str:
        parts = action.split("_")
        if action.startswith("interval_") and len(parts) == 2:
            minutes = max(3, min(120, int(parts[1])))
            self.ledger.set_state("auto_interval", str(minutes))
        elif action.startswith("window_") and len(parts) == 3:
            self.ledger.set_state("auto_peak_start", str(int(parts[1]) % 24))
            self.ledger.set_state("auto_peak_end", str(int(parts[2]) % 24))
        elif action.startswith("score_") and len(parts) == 2:
            self.ledger.set_state("auto_score", str(max(0, min(100, int(parts[1])))))
        elif action.startswith("cooldown_") and len(parts) == 2:
            self.ledger.set_state("auto_cooldown", str(max(0, min(1_440, int(parts[1])))))
        else:
            return "Unknown setting."
        self.ledger.set_state("next_auto_scan", "")
        return self.settings_message()

    def handle_text_setting(self, text: str) -> Optional[str]:
        parts = text.strip().lower().split()
        try:
            if len(parts) == 2 and parts[0] == "/interval":
                minutes = max(3, min(120, int(parts[1])))
                return self.set_preference(f"interval_{minutes}")
            if len(parts) == 3 and parts[0] == "/window":
                return self.set_preference(f"window_{int(parts[1]) % 24}_{int(parts[2]) % 24}")
            if len(parts) == 2 and parts[0] == "/cooldown":
                return self.set_preference(f"cooldown_{int(parts[1])}")
        except ValueError:
            return "Invalid setting. Example: /interval 7, /window 17 3, or /cooldown 120"
        return None

    def _inside_peak_window(self, now: datetime) -> bool:
        settings = self.automatic_settings()
        try:
            local_hour = now.astimezone(ZoneInfo(settings.auto_timezone)).hour
        except ZoneInfoNotFoundError:
            local_hour = now.astimezone(timezone.utc).hour
        start = settings.auto_peak_start_hour % 24
        end = settings.auto_peak_end_hour % 24
        if start == end:
            return True
        return start <= local_hour < end if start < end else local_hour >= start or local_hour < end

    def maybe_run_automatic(self, now: Optional[datetime] = None) -> Optional[str]:
        now = now or datetime.now(timezone.utc)
        settings = self.automatic_settings()
        if self.mode != "AUTOMATIC" or not self._inside_peak_window(now):
            return None
        due_text = self.ledger.get_state("next_auto_scan", "")
        if due_text and now < datetime.fromisoformat(due_text):
            return None
        next_scan = now + timedelta(minutes=settings.auto_scan_interval_minutes)
        self.ledger.set_state("next_auto_scan", next_scan.isoformat())
        try:
            from .live_data import run_automatic_scan
            result = run_automatic_scan(settings, now)
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
                action = callback.get("data", "")
                if action == "settings":
                    send_settings_menu(settings.telegram_token, chat_id, controller.settings_message())
                elif action == "main_menu":
                    send_control_menu(settings.telegram_token, chat_id, controller.status_message())
                elif action == "noop":
                    continue
                elif action.startswith(("interval_", "window_", "score_", "cooldown_")):
                    send_settings_menu(settings.telegram_token, chat_id, controller.set_preference(action))
                else:
                    send_control_menu(settings.telegram_token, chat_id, controller.handle(action))
            elif message and str(message.get("chat", {}).get("id", "")) == str(settings.telegram_chat_id):
                text = message.get("text", "")
                setting_reply = controller.handle_text_setting(text)
                if setting_reply:
                    send_settings_menu(settings.telegram_token, settings.telegram_chat_id, setting_reply)
                elif text.lower() in {"/start", "/menu", "/status"}:
                    send_control_menu(settings.telegram_token, settings.telegram_chat_id, controller.status_message())
        controller.maybe_run_automatic()
