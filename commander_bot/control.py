from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .access import TelegramAccess, user_database_path
from .notifications import (
    answer_callback, delete_webhook, get_updates, send_control_menu, send_launchpad_menu, send_paper_copy_menu,
    send_settings_menu, send_telegram, send_tester_menu, send_wallet_menu,
)
from .storage import Ledger


VALID_ACTIONS = {"scan_once", "status", "manual_on", "stop", "automatic", "emergency_stop", "leaderboard"}


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

    def tester_status_message(self) -> str:
        paper_copy = self.ledger.get_state("paper_copy_enabled", "OFF")
        scans = self._pref_int("tester_scan_count", 0)
        return (
            "🧪 DEGEN DETECTOR BETA ACCESS\n"
            "Role: Approved tester\n"
            "Research tools: ENABLED\n"
            "Trading: PAPER ONLY\n"
            "Wallet access: DISABLED\n"
            f"Personal paper copy: {paper_copy}\n"
            f"Research scans used: {scans}\n"
            "Owner controls and live execution: LOCKED"
        )

    def help_message(self) -> str:
        return (
            "📖 DEGEN DETECTOR BETA HELP\n\n"
            "⚡ Research Scan — show up to 10 ranked candidates that pass hard safety vetoes.\n"
            "🟢 Qualified — score meets the 75+ research threshold.\n"
            "🟡 Watchlist — passed hard vetoes but remains below the qualification threshold.\n"
            "🔥 Leaderboard — rank safe candidates by momentum and holding strength.\n"
            "🚀 Launchpads / PF — inspect Solana launch sources.\n"
            "👛 Wallet Tracker — monitor public addresses only.\n"
            "🧪 Paper Copy — simulate tracked-wallet activity.\n\n"
            f"Research scans have a {max(30, self.settings.tester_scan_cooldown_seconds)}-second tester cooldown. "
            "The bot never fills a list with rejected tokens just to reach ten.\n\n"
            "Use the bot in this private chat. Never send a seed phrase or private key. "
            "All beta results are research and simulation, not trade execution."
        )

    def handle_tester_scan(self, now: Optional[datetime] = None) -> str:
        now = now or datetime.now(timezone.utc)
        cooldown = max(30, self.settings.tester_scan_cooldown_seconds)
        last_text = self.ledger.get_state("last_tester_scan", "")
        if last_text:
            try:
                remaining = cooldown - int((now - datetime.fromisoformat(last_text)).total_seconds())
            except ValueError:
                remaining = 0
            if remaining > 0:
                return f"⏳ Research scan cooldown: try again in {remaining} seconds."
        self.ledger.set_state("last_tester_scan", now.isoformat())
        self.ledger.set_state("tester_scan_count", str(self._pref_int("tester_scan_count", 0) + 1))
        from .main import run_once
        run_once(self.settings)
        return f"✅ Research scan completed. Up to {max(1, min(10, self.settings.scan_result_limit))} ranked results were requested."

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
        if action == "leaderboard":
            if self.mode == "EMERGENCY_STOP":
                return "🚨 Leaderboard blocked: Emergency Stop is enabled."
            from .live_data import build_hot_leaderboard
            return build_hot_leaderboard(self.settings)
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

    def wallets_message(self) -> str:
        wallets = self.ledger.tracked_wallets()
        if not wallets:
            return "👛 WALLET / KOL TRACKER\n\nNo wallets tracked yet.\nUse /track ADDRESS LABEL"
        lines = ["👛 TRACKED WALLETS", ""]
        lines.extend(f"• {label}: {address}" for address, label, _ in wallets)
        lines.append("\nRead-only monitoring. No private keys or wallet access.")
        return "\n".join(lines)

    def wallet_help_message(self) -> str:
        return (
            "👛 WALLET TRACKER COMMANDS\n\n"
            "Add: /track ADDRESS LABEL\n"
            "Remove: /untrack ADDRESS\n"
            "List: /wallets\n"
            "Check now: /signals\n\n"
            "Paper copy: /paperon or /paperoff\n"
            "Portfolio: /portfolio\n"
            "Trader rankings: /traders\n\n"
            "Example: /track 7abc...xyz SmartTrader\n"
            "Only use public wallet addresses. Never send a seed phrase or private key."
        )

    def handle_wallet_command(self, text: str) -> Optional[str]:
        parts = text.strip().split(maxsplit=2)
        command = parts[0].lower() if parts else ""
        if command == "/track":
            if len(parts) < 2:
                return "Use: /track ADDRESS LABEL"
            from .wallet_tracker import valid_solana_address
            address = parts[1]
            if not valid_solana_address(address):
                return "That does not look like a valid Solana public address."
            label = parts[2][:40] if len(parts) == 3 else f"Wallet {address[:5]}"
            self.ledger.add_tracked_wallet(address, label)
            return f"✅ Tracking {label}. Existing activity is ignored; new movements will generate signals."
        if command == "/untrack":
            if len(parts) != 2:
                return "Use: /untrack ADDRESS"
            return "✅ Wallet removed." if self.ledger.remove_tracked_wallet(parts[1]) else "Wallet not found."
        if command == "/wallets":
            return self.wallets_message()
        if command == "/signals":
            return self.check_wallet_signals()
        if command == "/paperon":
            self.ledger.set_state("paper_copy_enabled", "ON")
            return "✅ Paper Copy enabled. Future tracked BUY/SELL signals will be simulated only."
        if command == "/paperoff":
            self.ledger.set_state("paper_copy_enabled", "OFF")
            return "⏹️ Paper Copy disabled. Existing paper positions remain in the portfolio."
        if command == "/portfolio":
            from .paper_copy import portfolio_message
            return portfolio_message(self.ledger)
        if command == "/traders":
            from .paper_copy import trader_rankings_message
            return trader_rankings_message(self.ledger)
        return None

    def paper_copy_message(self) -> str:
        from .paper_copy import paper_status_message
        return paper_status_message(self.settings, self.ledger)

    def handle_paper_action(self, action: str) -> str:
        if action == "paper_on":
            self.ledger.set_state("paper_copy_enabled", "ON")
            return self.paper_copy_message()
        if action == "paper_off":
            self.ledger.set_state("paper_copy_enabled", "OFF")
            return self.paper_copy_message()
        if action == "paper_portfolio":
            from .paper_copy import portfolio_message
            return portfolio_message(self.ledger)
        if action == "paper_traders":
            from .paper_copy import trader_rankings_message
            return trader_rankings_message(self.ledger)
        return self.paper_copy_message()

    def launchpad_message(self, action: str = "launchpads") -> str:
        from .launchpad_hub import build_launchpad_report, launchpad_help
        if action == "launch_help":
            return launchpad_help(self.settings)
        platform = action.removeprefix("launch_") if action.startswith("launch_") else "all"
        return build_launchpad_report(self.settings, platform)

    def check_wallet_signals(self) -> str:
        if self.mode == "EMERGENCY_STOP":
            return "🚨 Wallet checks blocked: Emergency Stop is enabled."
        if not self.ledger.tracked_wallets():
            return "No wallets tracked yet. Use /track ADDRESS LABEL"
        from .paper_copy import process_wallet_events
        from .wallet_tracker import poll_wallet_events
        events = poll_wallet_events(self.settings, self.ledger)
        messages = [event["message"] for event in events]
        messages.extend(process_wallet_events(self.settings, self.ledger, events))
        if not messages:
            return "📡 Wallet check complete: no new token movements."
        for message in messages[:-1]:
            send_telegram(self.settings.telegram_token, self.settings.telegram_chat_id, message)
        return messages[-1]

    def maybe_check_wallets(self, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)
        if self.mode == "EMERGENCY_STOP" or not self.ledger.tracked_wallets():
            return
        due_text = self.ledger.get_state("next_wallet_check", "")
        if due_text and now < datetime.fromisoformat(due_text):
            return
        self.ledger.set_state(
            "next_wallet_check",
            (now + timedelta(seconds=max(30, self.settings.wallet_check_interval_seconds))).isoformat(),
        )
        try:
            from .paper_copy import process_wallet_events
            from .wallet_tracker import poll_wallet_events
            events = poll_wallet_events(self.settings, self.ledger)
            messages = [event["message"] for event in events]
            messages.extend(process_wallet_events(self.settings, self.ledger, events))
            for message in messages:
                send_telegram(self.settings.telegram_token, self.settings.telegram_chat_id, message)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            return

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
    access = TelegramAccess.from_settings(settings)
    if not settings.telegram_token or not access.owner_id:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_ID before starting controls.")
    owner_settings = replace(settings, telegram_chat_id=access.owner_id)
    controller = BotController(owner_settings)
    tester_controllers: dict[str, BotController] = {}

    def tester_controller(chat_id: str) -> BotController:
        if chat_id not in tester_controllers:
            tester_settings = replace(
                settings,
                telegram_chat_id=chat_id,
                database_path=user_database_path(settings.database_path, chat_id),
            )
            tester_controllers[chat_id] = BotController(tester_settings)
        return tester_controllers[chat_id]

    def send_main_menu(chat_id: str, role: str, active: BotController) -> None:
        if role == "owner":
            send_control_menu(settings.telegram_token, chat_id, active.status_message())
        else:
            send_tester_menu(settings.telegram_token, chat_id, active.tester_status_message())

    delete_webhook(settings.telegram_token)
    send_control_menu(settings.telegram_token, access.owner_id, "Degen Detector controls are online.")
    offset: Optional[int] = None
    while True:
        for update in get_updates(settings.telegram_token, offset, settings.telegram_poll_seconds):
            offset = update["update_id"] + 1
            callback = update.get("callback_query")
            message = update.get("message")
            if callback:
                chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
                user_id = str(callback.get("from", {}).get("id", ""))
                chat_type = str(callback.get("message", {}).get("chat", {}).get("type", "private"))
                role = access.role(user_id)
                if chat_type != "private" or role == "unauthorized":
                    answer_callback(settings.telegram_token, callback["id"], "Not authorized")
                    continue
                answer_callback(settings.telegram_token, callback["id"])
                action = callback.get("data", "")
                active = controller if role == "owner" else tester_controller(chat_id)
                owner_only = {
                    "settings", "manual_on", "stop", "automatic", "emergency_stop",
                }
                if role != "owner" and (
                    action in owner_only or action.startswith(("interval_", "window_", "score_", "cooldown_"))
                ):
                    send_tester_menu(settings.telegram_token, chat_id, "🔒 Owner-only control.")
                elif action == "settings":
                    send_settings_menu(settings.telegram_token, chat_id, active.settings_message())
                elif action == "wallet_tracker":
                    send_wallet_menu(settings.telegram_token, chat_id, active.wallets_message())
                elif action == "wallet_list":
                    send_wallet_menu(settings.telegram_token, chat_id, active.wallets_message())
                elif action == "wallet_help":
                    send_wallet_menu(settings.telegram_token, chat_id, active.wallet_help_message())
                elif action == "wallet_signals":
                    send_wallet_menu(settings.telegram_token, chat_id, active.check_wallet_signals())
                elif action == "paper_copy":
                    send_paper_copy_menu(settings.telegram_token, chat_id, active.paper_copy_message())
                elif action == "launchpads" or action.startswith("launch_"):
                    send_launchpad_menu(settings.telegram_token, chat_id, active.launchpad_message(action))
                elif action.startswith("paper_"):
                    send_paper_copy_menu(settings.telegram_token, chat_id, active.handle_paper_action(action))
                elif action == "main_menu":
                    send_main_menu(chat_id, role, active)
                elif action == "help":
                    send_tester_menu(settings.telegram_token, chat_id, active.help_message())
                elif action == "noop":
                    continue
                elif action.startswith(("interval_", "window_", "score_", "cooldown_")):
                    send_settings_menu(settings.telegram_token, chat_id, active.set_preference(action))
                else:
                    if role == "tester" and action == "status":
                        reply = active.tester_status_message()
                    elif role == "tester" and action == "scan_once":
                        reply = active.handle_tester_scan()
                    else:
                        reply = active.handle(action)
                    if role == "owner":
                        send_control_menu(settings.telegram_token, chat_id, reply)
                    else:
                        send_tester_menu(settings.telegram_token, chat_id, reply)
            elif message:
                chat = message.get("chat", {})
                chat_id = str(chat.get("id", ""))
                chat_type = str(chat.get("type", "private"))
                user_id = str(message.get("from", {}).get("id", ""))
                text = message.get("text", "")
                if chat_type != "private":
                    group_command = text.lower().split("@", 1)[0]
                    if group_command == "/groupid" and access.role(user_id) == "owner":
                        send_telegram(
                            settings.telegram_token,
                            chat_id,
                            f"🔐 Degen Detector alert group ID: {chat_id}\nInteractive controls remain private-chat only.",
                        )
                    elif group_command in {"/start", "/menu"}:
                        send_telegram(
                            settings.telegram_token,
                            chat_id,
                            "For privacy and account safety, open Degen Detector directly and press Start in a private chat.",
                        )
                    continue
                role = access.role(user_id)
                if role == "unauthorized":
                    if text.lower() in {"/start", "/menu", "/id", "/whoami"}:
                        send_telegram(
                            settings.telegram_token,
                            chat_id,
                            "🔐 Beta access is pending.\n"
                            f"Your Telegram ID: {user_id}\n\n"
                            "Send this numeric ID to the Degen Detector owner. Never send a password, seed phrase or private key.",
                        )
                    continue
                active = controller if role == "owner" else tester_controller(chat_id)
                wallet_reply = active.handle_wallet_command(text)
                setting_reply = active.handle_text_setting(text) if role == "owner" and wallet_reply is None else None
                if wallet_reply:
                    send_wallet_menu(settings.telegram_token, chat_id, wallet_reply)
                elif setting_reply:
                    send_settings_menu(settings.telegram_token, chat_id, setting_reply)
                elif text.lower() in {"/start", "/menu", "/status"}:
                    send_main_menu(chat_id, role, active)
                elif text.lower() in {"/help", "/instructions"}:
                    if role == "owner":
                        send_control_menu(settings.telegram_token, chat_id, active.help_message())
                    else:
                        send_tester_menu(settings.telegram_token, chat_id, active.help_message())
        controller.maybe_run_automatic()
        controller.maybe_check_wallets()
        for active in tester_controllers.values():
            active.maybe_check_wallets()
