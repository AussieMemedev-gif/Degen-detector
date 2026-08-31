from typing import Iterable
from .config import Settings
from .models import CommanderDecision, TokenSnapshot


class ChiefCommander:
    weights = {"social": 0.20, "onchain": 0.30, "chart": 0.20, "risk": 0.30}
    stage15_weights = {
        "social": 0.12, "onchain": 0.22, "chart": 0.16,
        "risk": 0.25, "developer": 0.15, "narrative": 0.10,
    }

    def __init__(self, agents: Iterable, settings: Settings):
        self.agents = list(agents)
        self.settings = settings

    def decide(self, token: TokenSnapshot) -> CommanderDecision:
        reports = {report.agent: report for report in (agent.analyse(token) for agent in self.agents)}
        stage15 = {"developer", "narrative"}.issubset(reports)
        weights = dict(self.stage15_weights) if stage15 else dict(self.weights)
        if stage15:
            # Missing external evidence must not be mistaken for negative evidence.
            for name in ("developer", "narrative"):
                if reports[name].confidence in {"low", "unavailable"}:
                    weights.pop(name)
            total_weight = sum(weights.values())
            weights = {name: weight / total_weight for name, weight in weights.items()}
        missing = set(weights) - set(reports)
        if missing:
            raise ValueError(f"Missing required reports: {sorted(missing)}")
        score = round(sum(reports[name].score * weight for name, weight in weights.items()), 2)
        vetoes = [veto for report in reports.values() for veto in report.vetoes]
        approved = not vetoes and score >= self.settings.approval_score
        status = "PAPER_BUY_APPROVED" if approved else "REJECTED" if vetoes else "WATCHLIST"
        reasons = [
            f"{name}: {report.score:.1f}/100"
            + (" (low confidence; unweighted)" if name not in weights else "")
            for name, report in reports.items()
        ]
        return CommanderDecision(token.mint, token.symbol, score, status, reasons, vetoes, reports, self.settings.paper_position_usd if approved else 0)
