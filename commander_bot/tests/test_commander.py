import tempfile
import unittest
from dataclasses import replace
from commander_bot.agents import ChartTraderAgent, OnChainScoutAgent, RiskSecurityAgent, SocialAlphaAgent
from commander_bot.commander import ChiefCommander
from commander_bot.config import Settings
from commander_bot.main import demo_candidate
from commander_bot.storage import Ledger
from commander_bot.control import BotController


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


if __name__ == "__main__":
    unittest.main()
