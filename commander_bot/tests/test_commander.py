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
from commander_bot.live_data import snapshot_from_pair
from commander_bot.notifications import format_live_alert


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


if __name__ == "__main__":
    unittest.main()
