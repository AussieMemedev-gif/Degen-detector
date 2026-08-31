from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .access import TelegramAccess, user_database_path
from .notifications import (
    answer_callback, delete_webhook, get_updates, set_bot_commands, send_admin_menu, send_control_menu,
    send_discover_menu, send_launchpad_menu, send_learn_menu, send_paper_copy_menu, send_practice_menu,
    send_ca_chain_menu, send_real_trade_menu, send_scan_hub, send_settings_menu, send_telegram,
    send_tester_menu, send_wallet_menu,
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
            f"🛰️ DEGEN DETECTOR\n\n"
            f"System: 🟢 Online\n"
            f"Scan mode: {mode}\n"
            f"Trading: 🧪 PAPER ONLY (practice funds)\n"
            f"Wallet access: 🔒 None{detail}{auto_detail}\n\n"
            "Choose an option below. New here? Start with 🎓 Learn."
        )

    def tester_status_message(self) -> str:
        paper_copy = self.ledger.get_state("paper_copy_enabled", "OFF")
        scans = self._pref_int("tester_scan_count", 0)
        return (
            "💎 DEGEN DETECTOR\n\n"
            "System: 🟢 Online\n"
            "Access: ✅ Approved tester\n"
            "Research tools: ✅ Enabled\n"
            "Trading: 🧪 Practice only\n"
            "Wallet access: 🔒 None\n"
            f"Personal paper copy: {paper_copy}\n"
            f"Research scans used: {scans}\n\n"
            "Choose an option below. New here? Start with 🎓 Learn."
        )

    def scan_hub_message(self) -> str:
        return (
            "🔎 TOKEN RESEARCH SCAN\n\n"
            "Choose Solana for the full Commander and on-chain safety scan, or Robinhood Chain "
            "for an early market radar using indexed liquidity, volume and buy/sell activity.\n\n"
            "🟢 Qualified — strongest research result\n"
            "🟡 Watch — interesting, but needs caution\n"
            "🔴 Rejected — failed a safety rule\n\n"
            "Robinhood Chain is newer, so its radar is labelled market-first until equivalent "
            "contract and holder verification is available. A score is not a promise of profit."
        )

    def discover_message(self) -> str:
        return (
            "🔥 DISCOVER TOKENS\n\n"
            "Leaderboard ranks safer momentum candidates. Launchpads lets you browse "
            "Pump.fun, BONK, Raydium, Meteora and Jupiter sources.\n\n"
            "Use this area to build a watchlist. Use Scan for the fuller safety report."
        )

    def learn_message(self) -> str:
        return (
            "🎓 BEGINNER LEARNING CENTRE\n\n"
            "Learn the traffic-light scores, check risks before acting, and practise with "
            "fake money. You never need to connect a wallet or share a private key."
        )

    def score_guide_message(self) -> str:
        return (
            "🚦 HOW TO READ A RESULT\n\n"
            "🟢 QUALIFIED: Passed hard safety checks and reached the research threshold. "
            "Still high risk—check the chart and position size.\n\n"
            "🟡 WATCH: Passed hard vetoes but the overall evidence is weaker. Wait for "
            "confirmation rather than chasing.\n\n"
            "🔴 REJECTED: Failed one or more safety gates such as liquidity, holder "
            "concentration, active authorities, sell evidence or slippage. Do not paper-buy "
            "it from the result.\n\n"
            "The score combines Social 20%, On-chain 30%, Chart 20% and Risk 30%."
        )

    def safety_guide_message(self) -> str:
        return (
            "🛡️ FIVE-CHECK SAFETY RULE\n\n"
            "1. Prefer 🟢 results; never treat a score as a guarantee.\n"
            "2. Check liquidity, top-holder concentration and mint/freeze authority.\n"
            "3. Open the live chart; avoid sudden vertical pumps and collapsing volume.\n"
            "4. Practise first and use a small position you could afford to lose.\n"
            "5. Never send a seed phrase or private key—Degen Detector will never ask.\n\n"
            "Meme tokens can lose most or all of their value very quickly."
        )

    def practice_guide_message(self) -> str:
        return (
            "🎮 PRACTICE WALKTHROUGH\n\n"
            "1. Run a Scan.\n"
            "2. Open one result and tap Trade with Fake Money.\n"
            "3. Review the selected token and live chart.\n"
            "4. Choose a small SOL-size paper buy or enter a custom fake amount.\n"
            "5. Use Wallet to view the position.\n"
            "6. Sell 25%, 50%, 75% or 100% and review P&L.\n\n"
            "All funds are simulated. No blockchain transaction is created."
        )

    def admin_message(self) -> str:
        return self.status_message() + "\n\n🛠 OWNER CONTROLS\nChanges here affect global scanning."

    def help_message(self) -> str:
        return (
            "📖 DEGEN DETECTOR BETA HELP\n\n"
            "⚡ Research Scan — show up to 10 investigated candidates with green, amber or red status.\n"
            "🟢 Qualified — score meets the 75+ research threshold.\n"
            "🟡 Watchlist — passed hard vetoes but remains below the qualification threshold.\n"
            "🔴 Rejected — failed one or more hard safety checks; investigation only.\n"
            "🔥 Leaderboard — rank safe candidates by momentum and holding strength.\n"
            "🚀 Launchpads / PF — inspect Solana launch sources.\n"
            "👛 Wallet Tracker — monitor public addresses only.\n"
            "🧪 Paper Copy — simulate tracked-wallet activity.\n\n"
            "🎮 Practice Trade — trade live-priced tokens with isolated fake funds. "
            "Choose Trade with Fake Money below a scan result or use /trade TOKEN_MINT SYMBOL. "
            "The terminal includes fixed SOL buys, 25/50/75/100% exits, instant paper sell, "
            "wallet, history, all-time P&L and top gains.\n\n"
            f"Research scans have a {max(30, self.settings.tester_scan_cooldown_seconds)}-second tester cooldown. "
            "Rejected reports explain risk failures and can never create paper trades.\n\n"
            "Use the bot in this private chat. Never send a seed phrase or private key. "
            "All beta results are research and simulation, not trade execution."
        )

    def _practice(self):
        from .practice_trading import PracticeTrading
        return PracticeTrading(self.settings, self.ledger)

    def practice_message(self) -> str:
        return self._practice().terminal_message()

    def practice_chart(self) -> str:
        return self._practice().selected_chart

    def select_practice_token(self, mint: str, symbol: str = "") -> str:
        from .wallet_tracker import valid_solana_address
        if not valid_solana_address(mint):
            return "That does not look like a valid Solana token mint."
        practice = self._practice()
        try:
            selected = practice.select_token(mint, symbol)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            return "⚠️ Live token data is unavailable. Nothing was selected."
        return selected + "\n\n" + practice.terminal_message()

    def handle_practice_action(self, action: str) -> str:
        practice = self._practice()
        if action == "practice_snipe":
            return (
                "🎯 PAPER SNIPE MODE READY\n"
                "Use a SOL-size button below for an immediate simulated fill at the latest quote. "
                "Fees, slippage, cash and the hourly cap still apply.\n\n"
                + practice.terminal_message()
            )
        if action in {"practice_dashboard", "practice_refresh"}:
            return practice.terminal_message()
        if action == "practice_manual_buy":
            self.ledger.set_state("practice_pending_input", "CUSTOM_BUY")
            return (
                "✍️ CUSTOM PAPER BUY\n\n"
                "Enter a custom amount in either format:\n"
                "• 0.75 SOL or 0.05 ETH\n"
                "• $250 or 250 USD\n\n"
                "A plain number such as 0.75 is treated as SOL.\n"
                "Send /cancel to stop. The live quote, simulated fee, slippage, virtual cash "
                f"and ${self.settings.practice_hourly_buy_limit_usd:,.0f} rolling hourly limit "
                "will be checked before the fill."
            )
        if action == "practice_stop_loss":
            self.ledger.set_state("practice_pending_input", "STOP_LOSS")
            return (
                "🛡️ SET PRACTICE STOP LOSS\n\n"
                "Enter the percentage below your average entry that should trigger a full simulated sell.\n"
                "Examples: 10% or 25\n"
                "Enter 0 to remove the stop, or /cancel to stop.\n\n"
                "Stop checks use live quotes and can be delayed by API or service interruptions."
            )
        if action == "practice_manual_sell":
            self.ledger.set_state("practice_pending_input", "MANUAL_SELL")
            return (
                "✍️ MANUAL PAPER SELL\n\n"
                "Enter the percentage of the selected position to sell, from 1% to 100%.\n"
                "Examples: 33% or 100\n\nSend /cancel to stop."
            )
        if action == "practice_wallet":
            return practice.wallet_message()
        if action == "practice_profile":
            return practice.profile_message()
        if action == "practice_history":
            return practice.history_message()
        if action == "practice_pnl":
            return practice.pnl_message()
        if action == "practice_gains":
            return practice.top_gains_message()
        buy_sizes = {
            "practice_buy_0_5": 0.5,
            "practice_buy_1": 1.0,
            "practice_buy_2_5": 2.5,
            "practice_buy_5": 5.0,
            "practice_buy_10": 10.0,
        }
        if action in buy_sizes:
            return practice.buy_sol(buy_sizes[action])
        if action == "practice_instant_sell":
            return practice.sell_percent(100)
        if action.startswith("practice_sell_"):
            try:
                return practice.sell_percent(int(action.rsplit("_", 1)[1]))
            except ValueError:
                pass
        return practice.terminal_message()

    def handle_practice_command(self, text: str) -> Optional[str]:
        parts = text.strip().split(maxsplit=2)
        command = parts[0].lower() if parts else ""
        if command == "/cancel" and self.ledger.get_state("practice_pending_input", ""):
            self.ledger.set_state("practice_pending_input", "")
            return "Custom paper order cancelled."
        pending = self.ledger.get_state("practice_pending_input", "")
        if pending.startswith("CA_SEARCH:") and not command.startswith("/"):
            chain = pending.split(":", 1)[1]
            address = text.strip()
            if chain == "solana":
                from .wallet_tracker import valid_solana_address
                if not valid_solana_address(address):
                    return "That is not a valid Solana contract address. Paste the complete CA or send /cancel."
            elif not (address.startswith("0x") and len(address) == 42 and all(c in "0123456789abcdefABCDEF" for c in address[2:])):
                return "That is not a valid Robinhood Chain ERC-20 address. It must be 0x followed by 40 hexadecimal characters."
            self.ledger.set_state("practice_pending_input", "")
            from .practice_trading import asset_id
            return self.select_practice_token(asset_id(chain, address))
        if pending == "STOP_LOSS" and not command.startswith("/"):
            raw = text.strip().replace("%", "")
            try:
                percent = float(raw)
            except ValueError:
                return "Enter a number from 1 to 95, 0 to remove, or /cancel."
            self.ledger.set_state("practice_pending_input", "")
            return self._practice().set_stop_loss(percent)
        if pending == "MANUAL_SELL" and not command.startswith("/"):
            raw = text.strip().replace("%", "")
            try:
                percent = int(float(raw))
            except ValueError:
                return "Enter a sell percentage from 1 to 100, or /cancel."
            if percent < 1 or percent > 100:
                return "Enter a sell percentage from 1 to 100, or /cancel."
            self.ledger.set_state("practice_pending_input", "")
            return self._practice().sell_percent(percent)
        if pending == "CUSTOM_BUY" and not command.startswith("/"):
            return self._handle_custom_buy_text(text)
        if command == "/buy":
            if len(parts) < 2:
                return "Use /buy 0.75 SOL or /buy $250"
            return self._handle_custom_buy_text(" ".join(parts[1:]))
        if command == "/trade":
            if len(parts) < 2:
                return "Use: /trade TOKEN_MINT SYMBOL"
            symbol = parts[2] if len(parts) == 3 else ""
            return self.select_practice_token(parts[1], symbol)
        if command == "/paperwallet":
            return self._practice().wallet_message()
        if command == "/paperprofile":
            return self._practice().profile_message()
        if command == "/paperhistory":
            return self._practice().history_message()
        if command == "/paperpnl":
            return self._practice().pnl_message()
        if command == "/papergains":
            return self._practice().top_gains_message()
        return None

    def ca_search_message(self, chain: str) -> str:
        self.ledger.set_state("practice_pending_input", f"CA_SEARCH:{chain}")
        example = "a Solana base58 address" if chain == "solana" else "an EVM address beginning 0x"
        return (
            f"🔍 SEARCH {chain.upper()} CONTRACT ADDRESS\n\n"
            f"Paste the complete token CA ({example}) in your next message.\n\n"
            "The bot will verify the address, find its strongest live DEX pair and open it in the "
            "Practice terminal. No purchase happens automatically. Send /cancel to stop."
        )

    def real_trade_message(self) -> tuple[str, str]:
        mint = self._practice().selected_mint
        if not mint:
            return "Search a CA or select a scan result before opening real trade mode.", ""
        symbol = self._practice().selected_symbol or mint[:6]
        chain, address = self._practice().selected_chain, self._practice().selected_address
        venue = "Uniswap on Robinhood Chain" if chain == "robinhood" else "Jupiter on Solana"
        return (
            "🔐 OWNER REAL TRADE — WALLET APPROVAL REQUIRED\n\n"
            f"Selected: {symbol}\nNetwork: {chain.title()}\nCA: {address}\nVenue: {venue}\n\n"
            "Buy and Sell open the self-custodial trading interface with this CA selected. Review the "
            "token, quote, price impact, slippage and destination before approving in your wallet.\n\n"
            "Degen Detector does not store a private key and cannot approve the transaction for you.",
            address,
        )

    def _handle_custom_buy_text(self, text: str) -> str:
        raw = text.strip().upper().replace(",", "")
        is_usd = raw.startswith("$") or raw.endswith(" USD")
        number = raw.removeprefix("$").removesuffix(" USD").removesuffix(" SOL").removesuffix(" ETH").strip()
        try:
            amount = float(number)
        except ValueError:
            return "Invalid amount. Enter 0.75 SOL, $250, or send /cancel."
        if amount <= 0 or amount > 1_000_000:
            return "Enter an amount greater than zero and within the paper account limits."
        self.ledger.set_state("practice_pending_input", "")
        practice = self._practice()
        return practice.buy_usd(amount) if is_usd else practice.buy_sol(amount)

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

    def maybe_check_practice_stops(self, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)
        due_text = self.ledger.get_state("next_practice_stop_check", "")
        if due_text and now < datetime.fromisoformat(due_text):
            return
        self.ledger.set_state("next_practice_stop_check", (now + timedelta(seconds=30)).isoformat())
        for message in self._practice().check_stop_losses():
            send_telegram(self.settings.telegram_token, self.settings.telegram_chat_id, message)

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
    set_bot_commands(settings.telegram_token)
    send_control_menu(settings.telegram_token, access.owner_id, controller.status_message())
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
                    "settings", "admin_hub", "manual_on", "stop", "automatic_ask", "automatic_confirm",
                    "emergency_ask", "emergency_confirm", "real_trade",
                }
                if role != "owner" and (
                    action in owner_only or action.startswith(("interval_", "window_", "score_", "cooldown_"))
                ):
                    send_tester_menu(settings.telegram_token, chat_id, "🔒 Owner-only control.")
                elif action == "ca_search":
                    send_ca_chain_menu(settings.telegram_token, chat_id,
                        "🔍 CHOOSE A NETWORK\n\nSolana uses base58 CAs. Robinhood Chain uses EVM 0x addresses and ETH for gas.")
                elif action in {"ca_chain_solana", "ca_chain_robinhood"}:
                    chain = action.removeprefix("ca_chain_")
                    send_practice_menu(settings.telegram_token, chat_id, active.ca_search_message(chain))
                elif action == "real_trade":
                    message_text, mint = active.real_trade_message()
                    if mint:
                        send_real_trade_menu(settings.telegram_token, chat_id, message_text, mint, active._practice().selected_chain)
                    else:
                        send_admin_menu(settings.telegram_token, chat_id, message_text)
                elif action == "scan_hub":
                    send_scan_hub(settings.telegram_token, chat_id, active.scan_hub_message())
                elif action == "robinhood_scan":
                    from .live_data import build_robinhood_meme_report
                    send_scan_hub(settings.telegram_token, chat_id, build_robinhood_meme_report(active.settings))
                elif action == "discover_hub":
                    send_discover_menu(settings.telegram_token, chat_id, active.discover_message())
                elif action == "early_mooners":
                    from .live_data import build_early_mooner_report
                    send_discover_menu(settings.telegram_token, chat_id, build_early_mooner_report(active.settings))
                elif action == "learn_hub":
                    send_learn_menu(settings.telegram_token, chat_id, active.learn_message())
                elif action == "score_guide":
                    send_learn_menu(settings.telegram_token, chat_id, active.score_guide_message())
                elif action == "safety_guide":
                    send_learn_menu(settings.telegram_token, chat_id, active.safety_guide_message())
                elif action == "practice_guide":
                    send_learn_menu(settings.telegram_token, chat_id, active.practice_guide_message())
                elif action == "admin_hub":
                    send_admin_menu(settings.telegram_token, chat_id, active.admin_message())
                elif action == "automatic_ask":
                    send_admin_menu(settings.telegram_token, chat_id,
                        "🕒 ENABLE AUTOMATIC SCANNING?\n\nThe bot will scan on schedule using your current settings. "
                        "This remains research and paper-only.", "automatic")
                elif action == "emergency_ask":
                    send_admin_menu(settings.telegram_token, chat_id,
                        "🚨 ENABLE EMERGENCY STOP?\n\nThis immediately blocks manual scans, automatic scans and wallet checks.",
                        "emergency")
                elif action == "automatic_confirm":
                    send_admin_menu(settings.telegram_token, chat_id, active.handle("automatic"))
                elif action == "emergency_confirm":
                    send_admin_menu(settings.telegram_token, chat_id, active.handle("emergency_stop"))
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
                elif action.startswith("practice_select:"):
                    mint = action.split(":", 1)[1]
                    send_practice_menu(
                        settings.telegram_token, chat_id, active.select_practice_token(mint), active.practice_chart()
                    )
                elif action == "practice_dashboard" or action.startswith("practice_"):
                    send_practice_menu(
                        settings.telegram_token, chat_id, active.handle_practice_action(action), active.practice_chart()
                    )
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
                practice_reply = active.handle_practice_command(text)
                wallet_reply = active.handle_wallet_command(text) if practice_reply is None else None
                setting_reply = (
                    active.handle_text_setting(text)
                    if role == "owner" and practice_reply is None and wallet_reply is None else None
                )
                if practice_reply:
                    send_practice_menu(
                        settings.telegram_token, chat_id, practice_reply, active.practice_chart()
                    )
                elif wallet_reply:
                    send_wallet_menu(settings.telegram_token, chat_id, wallet_reply)
                elif setting_reply:
                    send_settings_menu(settings.telegram_token, chat_id, setting_reply)
                elif text.lower() in {"/start", "/menu", "/status"}:
                    send_main_menu(chat_id, role, active)
                elif text.lower() == "/scan":
                    send_scan_hub(settings.telegram_token, chat_id, active.handle_tester_scan() if role == "tester" else active.handle("scan_once"))
                elif text.lower() == "/learn":
                    send_learn_menu(settings.telegram_token, chat_id, active.learn_message())
                elif text.lower() in {"/help", "/instructions"}:
                    if role == "owner":
                        send_control_menu(settings.telegram_token, chat_id, active.help_message())
                    else:
                        send_tester_menu(settings.telegram_token, chat_id, active.help_message())
        controller.maybe_run_automatic()
        controller.maybe_check_wallets()
        controller.maybe_check_practice_stops()
        for active in tester_controllers.values():
            active.maybe_check_wallets()
            active.maybe_check_practice_stops()
