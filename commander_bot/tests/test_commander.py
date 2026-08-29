import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch
from commander_bot.agents import ChartTraderAgent, OnChainScoutAgent, RiskSecurityAgent, SocialAlphaAgent
from commander_bot.commander import ChiefCommander
from commander_bot.config import Settings
from commander_bot.main import demo_candidate
from commander_bot.storage import Ledger
from commander_bot.control import BotController
from commander_bot.live_data import (
    format_hot_leaderboard, format_scan_summary, hot_score, investigated_scan_results,
    research_class, snapshot_from_pair, visible_scan_results,
)
from commander_bot.notifications import (
    format_live_alert, practice_keyboard, research_result_keyboard, telegram_request,
)
from commander_bot.wallet_tracker import transaction_movements, valid_solana_address
from commander_bot.paper_copy import portfolio_message, process_wallet_events, trader_rankings_message
from commander_bot.launchpad_hub import identify_launchpad, _bundle_estimate, _sniper_estimate
from commander_bot.access import TelegramAccess, parse_telegram_ids, user_database_path
from commander_bot.notifications import tester_keyboard
from commander_bot.practice_trading import PracticeTrading


class CommanderTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(database_path=":memory:")
        agents = [SocialAlphaAgent(), OnChainScoutAgent(), ChartTraderAgent(), RiskSecurityAgent(self.settings)]
        self.commander = ChiefCommander(agents, self.settings)

    def test_good_candidate_is_paper_only(self):
        decision = self.commander.decide(demo_candidate())
        self.assertEqual(decision.status, "PAPER_BUY_APPROVED")
        self.assertGreaterEqual(decision.score, self.settings.approval_score)

    def test_risk_veto_overrides_other_agents(self):
        risky = replace(demo_candidate(), liquidity_usd=1_000, sellable=False)
        decision = self.commander.decide(risky)
        self.assertEqual(decision.status, "REJECTED")
        self.assertIn("sellability check failed", decision.vetoes)

    def test_decision_is_audited(self):
        ledger = Ledger(":memory:")
        token = demo_candidate()
        ledger.record(token, self.commander.decide(token))
        count = ledger.connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        self.assertEqual(count, 1)

    def test_control_modes_are_persistent_and_paper_only(self):
        with tempfile.NamedTemporaryFile() as database:
            settings = Settings(database_path=database.name, manual_session_minutes=30)
            controller = BotController(settings)
            self.assertIn("Manual mode enabled", controller.handle("manual_on"))
            restarted = BotController(settings)
            self.assertEqual(restarted.mode, "MANUAL")
            self.assertIn("PAPER ONLY", restarted.status_message())
            restarted.handle("emergency_stop")
            self.assertEqual(restarted.mode, "EMERGENCY_STOP")
            self.assertIn("Scan blocked", restarted.handle("scan_once"))

    def test_automatic_runs_only_in_peak_window_and_waits_for_interval(self):
        with tempfile.NamedTemporaryFile() as database:
            settings = Settings(
                database_path=database.name,
                auto_timezone="UTC",
                auto_peak_start_hour=18,
                auto_peak_end_hour=2,
                auto_scan_interval_minutes=15,
            )
            controller = BotController(settings)
            controller.handle("automatic")
            outside = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
            inside = datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc)
            self.assertIsNone(controller.maybe_run_automatic(outside))
            with patch("commander_bot.live_data.run_automatic_scan", return_value="scan complete") as scan:
                self.assertEqual(controller.maybe_run_automatic(inside), "scan complete")
                self.assertIsNone(controller.maybe_run_automatic(inside))
                scan.assert_called_once()

    def test_alert_history_suppresses_recent_duplicates(self):
        ledger = Ledger(":memory:")
        now = datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc)
        self.assertFalse(ledger.recently_alerted("mint", 180, now))
        ledger.record_alert("mint", now)
        self.assertTrue(ledger.recently_alerted("mint", 180, now))

    def test_preferences_can_be_changed_without_redeploying(self):
        controller = BotController(Settings(database_path=":memory:"))
        controller.set_preference("interval_5")
        controller.set_preference("window_20_4")
        controller.set_preference("score_70")
        controller.set_preference("cooldown_60")
        settings = controller.automatic_settings()
        self.assertEqual(settings.auto_scan_interval_minutes, 5)
        self.assertEqual((settings.auto_peak_start_hour, settings.auto_peak_end_hour), (20, 4))
        self.assertEqual(settings.auto_alert_min_score, 70)
        self.assertEqual(settings.auto_duplicate_cooldown_minutes, 60)
        self.assertIn("/interval 7", controller.settings_message())

    def test_custom_interval_and_window_commands(self):
        controller = BotController(Settings(database_path=":memory:"))
        controller.handle_text_setting("/interval 7")
        controller.handle_text_setting("/window 17 3")
        controller.handle_text_setting("/cooldown 120")
        settings = controller.automatic_settings()
        self.assertEqual(settings.auto_scan_interval_minutes, 7)
        self.assertEqual((settings.auto_peak_start_hour, settings.auto_peak_end_hour), (17, 3))
        self.assertEqual(settings.auto_duplicate_cooldown_minutes, 120)

    def test_live_pair_mapping_uses_real_pair_fields_and_no_fake_social_data(self):
        pair = {
            "baseToken": {"symbol": "LIVE"}, "priceUsd": "0.01",
            "liquidity": {"usd": 50000}, "volume": {"m5": 12000, "h1": 60000},
            "txns": {"m5": {"buys": 40, "sells": 20}},
            "priceChange": {"m5": 4, "h1": 12}, "pairCreatedAt": 1_700_000_000_000,
            "url": "https://dexscreener.com/solana/pair", "dexId": "raydium",
        }
        risk = {"top10_holder_pct": 20, "mint_authority_active": False, "freeze_authority_active": False}
        token = snapshot_from_pair("mint", pair, risk)
        self.assertEqual(token.buys_5m, 40)
        self.assertEqual(token.buy_sell_ratio, 2)
        self.assertFalse(token.social_data_available)
        self.assertEqual(token.dex_id, "raydium")
        self.assertIn("dexscreener.com", token.chart_url)

    def test_live_report_explains_metrics_and_safety(self):
        token = replace(
            demo_candidate(),
            social_data_available=False,
            chart_url="https://dexscreener.com/solana/pair",
            dex_id="raydium",
        )
        message = format_live_alert(token, self.commander.decide(token))
        self.assertIn("LIVE DATA / PAPER ONLY", message)
        self.assertIn("SAFETY", message)
        self.assertIn("Pool age", message)
        self.assertIn("No wallet access", message)
        self.assertIn("https://dexscreener.com/solana/pair", message)

    def test_hot_leaderboard_rewards_holding_and_rejects_dumping(self):
        holding = replace(
            demo_candidate(),
            symbol="HOLD",
            price_change_5m_pct=4,
            price_change_1h_pct=25,
            chart_url="https://dexscreener.com/solana/hold",
        )
        dumping = replace(demo_candidate(), symbol="DUMP", price_change_5m_pct=-20)
        holding_decision = self.commander.decide(holding)
        dumping_decision = self.commander.decide(dumping)
        self.assertGreaterEqual(hot_score(holding, holding_decision), 0)
        self.assertEqual(hot_score(dumping, dumping_decision), -1)
        message = format_hot_leaderboard([(holding, holding_decision), (dumping, dumping_decision)])
        self.assertIn("HOT TOKEN LEADERBOARD", message)
        self.assertIn("HOLD", message)
        self.assertNotIn("DUMP —", message)

    def test_wallet_tracker_management_is_persistent(self):
        controller = BotController(Settings(database_path=":memory:"))
        address = "11111111111111111111111111111111"
        self.assertTrue(valid_solana_address(address))
        self.assertIn("Tracking", controller.handle_wallet_command(f"/track {address} Demo KOL"))
        self.assertIn("Demo KOL", controller.wallets_message())
        self.assertIn("removed", controller.handle_wallet_command(f"/untrack {address}"))

    def test_wallet_transaction_movements_are_read_only_signals(self):
        wallet = "11111111111111111111111111111111"
        transaction = {
            "meta": {
                "err": None,
                "preBalances": [2_000_000_000],
                "postBalances": [1_000_000_000],
                "preTokenBalances": [{"owner": wallet, "mint": "mint", "uiTokenAmount": {"uiAmountString": "0"}}],
                "postTokenBalances": [{"owner": wallet, "mint": "mint", "uiTokenAmount": {"uiAmountString": "100"}}],
            },
            "transaction": {"message": {"accountKeys": [wallet]}},
        }
        movements = transaction_movements(transaction, wallet)
        self.assertEqual(movements[0]["action"], "BUY / TOKEN IN")
        self.assertEqual(movements[0]["amount"], 100)

    def test_paper_copy_is_opt_in_and_never_opens_when_disabled(self):
        ledger = Ledger(":memory:")
        event = {
            "wallet_address": "11111111111111111111111111111111",
            "wallet_label": "Demo Trader", "signature": "buy-sig",
            "mint": "demo-mint", "action": "BUY / TOKEN IN",
        }
        messages = process_wallet_events(self.settings, ledger, [event], price_lookup=lambda _: 0.50)
        self.assertEqual(messages, [])
        self.assertEqual(ledger.open_paper_positions(), [])

    def test_paper_copy_records_pnl_and_trader_performance(self):
        ledger = Ledger(":memory:")
        ledger.set_state("paper_copy_enabled", "ON")
        wallet = "11111111111111111111111111111111"
        buy = {
            "wallet_address": wallet, "wallet_label": "Demo Trader", "signature": "buy-sig",
            "mint": "demo-mint", "action": "BUY / TOKEN IN",
        }
        sell = {**buy, "signature": "sell-sig", "action": "SELL / TOKEN OUT"}
        opened = process_wallet_events(self.settings, ledger, [buy], price_lookup=lambda _: 0.50)
        self.assertIn("PAPER COPY — OPENED", opened[0])
        self.assertIn("Open positions: 1", portfolio_message(ledger))
        closed = process_wallet_events(self.settings, ledger, [sell], price_lookup=lambda _: 1.00)
        self.assertIn("+25.00 USD", closed[0])
        self.assertIn("Win rate: 100%", trader_rankings_message(ledger))

    def test_paper_copy_telegram_commands_toggle_and_report(self):
        controller = BotController(Settings(database_path=":memory:"))
        self.assertIn("enabled", controller.handle_wallet_command("/paperon"))
        self.assertEqual(controller.ledger.get_state("paper_copy_enabled"), "ON")
        self.assertIn("PAPER PORTFOLIO", controller.handle_wallet_command("/portfolio"))
        self.assertIn("disabled", controller.handle_wallet_command("/paperoff"))

    def test_pump_launch_is_identified_from_mint_suffix(self):
        token = replace(demo_candidate(), mint="DemoMintpump", dex_id="pumpswap")
        identity = identify_launchpad(token)
        self.assertEqual(identity.key, "pf")
        self.assertEqual(identity.confidence, "high")

    def test_launch_forensics_are_bounded_and_labelled_as_estimates(self):
        token = replace(demo_candidate(), top10_holder_pct=35, pool_age_minutes=10, buys_5m=400)
        bundle, bundle_confidence = _bundle_estimate(token)
        sniper, sniper_confidence = _sniper_estimate(token)
        self.assertTrue(0 <= bundle <= 100)
        self.assertTrue(0 <= sniper <= 100)
        self.assertEqual(bundle_confidence, "low")
        self.assertEqual(sniper_confidence, "low")

    def test_beta_access_separates_owner_testers_and_unknown_users(self):
        settings = Settings(
            telegram_chat_id="111",
            telegram_owner_id="111",
            telegram_tester_ids="222, 333 222",
        )
        access = TelegramAccess.from_settings(settings)
        self.assertEqual(access.role("111"), "owner")
        self.assertEqual(access.role("222"), "tester")
        self.assertEqual(access.role("999"), "unauthorized")
        self.assertEqual(parse_telegram_ids("222, 333"), frozenset({"222", "333"}))

    def test_tester_menu_has_no_owner_controls(self):
        actions = {
            button["callback_data"]
            for row in tester_keyboard()["inline_keyboard"]
            for button in row
        }
        self.assertIn("launchpads", actions)
        self.assertIn("wallet_tracker", actions)
        self.assertNotIn("automatic", actions)
        self.assertNotIn("emergency_stop", actions)
        self.assertNotIn("settings", actions)

    def test_tester_database_paths_are_isolated(self):
        owner = "commander_bot.db"
        first = user_database_path(owner, "222")
        second = user_database_path(owner, "333")
        self.assertNotEqual(first, owner)
        self.assertNotEqual(first, second)
        self.assertEqual(user_database_path(":memory:", "222"), ":memory:")

    @patch("commander_bot.notifications.urllib.request.urlopen")
    def test_telegram_delete_webhook_request_is_supported(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"ok": true, "result": true}'
        result = telegram_request("test-token", "deleteWebhook", {"drop_pending_updates": False})
        self.assertTrue(result["ok"])
        request = urlopen.call_args.args[0]
        self.assertIn("deleteWebhook", request.full_url)

    def test_ranked_scan_shows_up_to_ten_non_rejected_results(self):
        safe_results = []
        for index in range(12):
            token = replace(demo_candidate(), mint=f"mint-{index}", symbol=f"SAFE{index}")
            safe_results.append((token, self.commander.decide(token)))
        rejected_token = replace(demo_candidate(), mint="rejected", liquidity_usd=1_000, sellable=False)
        results = safe_results + [(rejected_token, self.commander.decide(rejected_token))]
        visible = visible_scan_results(results, 10)
        self.assertEqual(len(visible), 10)
        self.assertTrue(all(decision.status != "REJECTED" for _, decision in visible))
        summary = format_scan_summary(visible, results, len(results), len(results), 75, 10)
        self.assertIn("Showing: 10 of up to 10", summary)
        self.assertIn("Rejected investigations: 1", summary)

    def test_investigation_scan_can_show_rejected_tokens_without_qualifying_them(self):
        safe = replace(demo_candidate(), mint="safe", symbol="SAFE")
        rejected = replace(demo_candidate(), mint="risk", symbol="RISK", liquidity_usd=1_000, sellable=False)
        results = [(safe, self.commander.decide(safe)), (rejected, self.commander.decide(rejected))]
        displayed = investigated_scan_results(results, 10, 75)
        self.assertEqual(len(displayed), 2)
        self.assertEqual(research_class(displayed[0][1], 75), "QUALIFIED RESEARCH")
        self.assertEqual(research_class(displayed[1][1], 75), "REJECTED INVESTIGATION")
        self.assertEqual(displayed[1][1].paper_position_usd, 0)
        summary = format_scan_summary(
            displayed, results, 2, 3, 75, 10, {"On-chain verification incomplete": 1}
        )
        self.assertIn("Incomplete data: 1", summary)
        self.assertIn("sellability check failed", summary)

    def test_tester_scan_cooldown_prevents_repeated_api_use(self):
        controller = BotController(Settings(database_path=":memory:", tester_scan_cooldown_seconds=90))
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        with patch("commander_bot.main.run_once", return_value="done") as scan:
            first = controller.handle_tester_scan(now)
            second = controller.handle_tester_scan(now)
        self.assertIn("completed", first)
        self.assertIn("cooldown", second)
        scan.assert_called_once()

    def test_ledger_creates_parent_directory_for_persistent_volume_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/nested/commander_bot.db"
            ledger = Ledger(path)
            ledger.set_state("persistent", "yes")
            self.assertEqual(ledger.get_state("persistent"), "yes")

    def test_practice_terminal_buy_partial_sell_and_performance(self):
        settings = Settings(
            database_path=":memory:", practice_starting_balance_usd=10_000,
            practice_hourly_buy_limit_usd=1_000, practice_fee_pct=0.5,
            practice_slippage_pct=1,
        )
        ledger = Ledger(":memory:")
        practice = PracticeTrading(settings, ledger)
        ledger.set_state("practice_selected_mint", "demo-mint")
        ledger.set_state("practice_selected_symbol", "DEMO")
        now = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)
        buy = practice.buy_sol(1, token_price=2, sol_price=100, now=now)
        self.assertIn("PAPER BUY FILLED", buy)
        self.assertAlmostEqual(ledger.practice_cash(), 9_899.50)
        position = ledger.practice_position("demo-mint")
        self.assertAlmostEqual(position[2], 100 / 2.02)
        self.assertAlmostEqual(practice.hourly_remaining(now), 899.50)
        sold = practice.sell_percent(50, token_price=4, now=now)
        self.assertIn("PAPER SELL FILLED", sold)
        self.assertGreater(ledger.practice_statistics()[2], 0)
        self.assertAlmostEqual(ledger.practice_position("demo-mint")[2], position[2] / 2)
        self.assertIn("DEMO", practice.history_message())
        self.assertIn("100.0%", practice.pnl_message(price_lookup=lambda _: 4))
        self.assertIn("DEMO", practice.top_gains_message())
        closed = practice.sell_percent(100, token_price=4, now=now)
        self.assertIn("PAPER SELL FILLED", closed)
        self.assertIsNone(ledger.practice_position("demo-mint"))

    def test_practice_terminal_enforces_rolling_hourly_buy_limit(self):
        settings = Settings(
            database_path=":memory:", practice_starting_balance_usd=10_000,
            practice_hourly_buy_limit_usd=1_000, practice_fee_pct=0.5,
            practice_slippage_pct=1,
        )
        ledger = Ledger(":memory:")
        practice = PracticeTrading(settings, ledger)
        ledger.set_state("practice_selected_mint", "demo-mint")
        ledger.set_state("practice_selected_symbol", "DEMO")
        blocked = practice.buy_sol(
            10, token_price=2, sol_price=100,
            now=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        )
        self.assertIn("Hourly paper-buy limit exceeded", blocked)
        self.assertEqual(ledger.practice_cash(), 10_000)
        self.assertEqual(ledger.practice_history(), [])

    def test_practice_interface_has_required_safe_controls(self):
        keyboard = practice_keyboard("https://dexscreener.com/solana/demo")
        actions = {
            button.get("callback_data")
            for row in keyboard["inline_keyboard"] for button in row
            if button.get("callback_data")
        }
        for action in {
            "practice_profile", "practice_wallet", "practice_history", "practice_pnl", "practice_gains",
            "practice_buy_0_5", "practice_buy_1", "practice_buy_2_5",
            "practice_buy_5", "practice_buy_10", "practice_sell_25",
            "practice_sell_50", "practice_sell_75", "practice_sell_100",
            "practice_instant_sell",
        }:
            self.assertIn(action, actions)
        self.assertFalse(any("live" in (action or "") for action in actions))
        mint = "11111111111111111111111111111111"
        result_keyboard = research_result_keyboard(mint, "https://dexscreener.com/solana/demo")
        callback = result_keyboard["inline_keyboard"][0][0]["callback_data"]
        self.assertEqual(callback, f"practice_select:{mint}")
        self.assertLessEqual(len(callback.encode()), 64)

    def test_practice_accounts_are_isolated_per_user_database(self):
        with tempfile.TemporaryDirectory() as directory:
            first_path = f"{directory}/user-1.db"
            second_path = f"{directory}/user-2.db"
            settings = Settings(
                practice_starting_balance_usd=10_000, practice_hourly_buy_limit_usd=1_000,
                practice_fee_pct=0.5, practice_slippage_pct=1,
            )
            first = Ledger(first_path)
            second = Ledger(second_path)
            first_terminal = PracticeTrading(settings, first)
            PracticeTrading(settings, second)
            first.set_state("practice_selected_mint", "demo-mint")
            first.set_state("practice_selected_symbol", "DEMO")
            first_terminal.buy_sol(1, token_price=2, sol_price=100)
            self.assertLess(first.practice_cash(), second.practice_cash())
            self.assertEqual(second.practice_positions(), [])


if __name__ == "__main__":
    unittest.main()
