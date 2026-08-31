from .config import Settings
from .models import AgentReport, TokenSnapshot


def clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


class SocialAlphaAgent:
    name = "social"

    def analyse(self, token: TokenSnapshot) -> AgentReport:
        if not token.social_data_available:
            return AgentReport(self.name, 0.0, "low", ["social/KOL feed not connected in Live Data V3"])
        score = min(token.social_mentions_15m / 5, 35)
        score += min(max(token.social_velocity_pct, 0) / 4, 35)
        score += min(token.trusted_kol_mentions * 10, 30)
        reasons = [f"{token.social_mentions_15m} mentions/15m", f"social velocity {token.social_velocity_pct:.1f}%"]
        if token.trusted_kol_mentions:
            reasons.append(f"{token.trusted_kol_mentions} trusted KOL mention(s)")
        return AgentReport(self.name, clamp(score), "high" if score >= 75 else "medium", reasons)


class OnChainScoutAgent:
    name = "onchain"

    def analyse(self, token: TokenSnapshot) -> AgentReport:
        score = min(token.liquidity_usd / 1_500, 30)
        score += min(token.volume_5m_usd / 1_000, 25)
        score += min(token.buys_5m / 2, 25)
        score += min(max(token.buy_sell_ratio - 1, 0) * 10, 20)
        reasons = [f"liquidity ${token.liquidity_usd:,.0f}", f"{token.buys_5m} buy transactions/5m", f"buy/sell ratio {token.buy_sell_ratio:.2f}"]
        return AgentReport(self.name, clamp(score), "high" if score >= 75 else "medium", reasons)


class ChartTraderAgent:
    name = "chart"

    def analyse(self, token: TokenSnapshot) -> AgentReport:
        momentum = max(0, 45 - abs(token.price_change_5m_pct - 8) * 2)
        trend = min(max(token.price_change_1h_pct, 0) * 1.2, 30)
        volume = min(max(token.volume_change_pct, 0) / 4, 25)
        score = momentum + trend + volume
        reasons = [f"5m price {token.price_change_5m_pct:+.1f}%", f"1h price {token.price_change_1h_pct:+.1f}%", f"volume acceleration {token.volume_change_pct:+.1f}%"]
        return AgentReport(self.name, clamp(score), "high" if score >= 75 else "medium", reasons)


class RiskSecurityAgent:
    name = "risk"

    def __init__(self, settings: Settings):
        self.settings = settings

    def analyse(self, token: TokenSnapshot) -> AgentReport:
        vetoes = []
        if token.liquidity_usd < self.settings.min_liquidity_usd:
            vetoes.append("liquidity below safety floor")
        if token.top10_holder_pct > self.settings.max_top10_holder_pct:
            vetoes.append("top-10 holder concentration too high")
        if token.mint_authority_active:
            vetoes.append("mint authority active")
        if token.freeze_authority_active:
            vetoes.append("freeze authority active")
        if not token.sellable:
            vetoes.append("sellability check failed")
        if token.estimated_slippage_pct > self.settings.max_slippage_pct:
            vetoes.append("estimated slippage above limit")
        concentration_penalty = max(0, token.top10_holder_pct - 15) * 2
        slippage_penalty = token.estimated_slippage_pct * 8
        score = 100 - concentration_penalty - slippage_penalty - len(vetoes) * 20
        reasons = [f"top-10 holders {token.top10_holder_pct:.1f}%", f"estimated slippage {token.estimated_slippage_pct:.2f}%"]
        return AgentReport(self.name, clamp(score), "high" if not vetoes else "low", reasons, vetoes)
