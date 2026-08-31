from typing import Iterable
from .config import Settings
from .models import CommanderDecision, TokenSnapshot


class ChiefCommander:
    weights = {"social": 0.20, "onchain": 0.30, "chart": 0.20, "risk": 0.30}

    def __init__(self, agents: Iterable, settings: Settings):
        self.agents = list(agents)
        self.settings = settings

    def decide(self, token: TokenSnapshot) -> CommanderDecision:
        reports = {report.agent: report for report in (agent.analyse(token) for agent in self.agents)}
        missing = set(self.weights) - set(reports)
        if missing:
            raise ValueError(f"Missing required reports: {sorted(missing)}")
        score = round(sum(reports[name].score * weight for name, weight in self.weights.items()), 2)
        vetoes = [veto for report in reports.values() for veto in report.vetoes]
        approved = not vetoes and score >= self.settings.approval_score
        status = "PAPER_BUY_APPROVED" if approved else "REJECTED" if vetoes else "WATCHLIST"
        reasons = [f"{name}: {reports[name].score:.1f}/100" for name in self.weights]
        return CommanderDecision(token.mint, token.symbol, score, status, reasons, vetoes, reports, self.settings.paper_position_usd if approved else 0)

