from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


@dataclass(frozen=True)
class TokenSnapshot:
    mint: str
    symbol: str
    price_usd: float
    liquidity_usd: float
    volume_5m_usd: float
    volume_change_pct: float
    buys_5m: int
    buy_sell_ratio: float
    top10_holder_pct: float
    mint_authority_active: bool
    freeze_authority_active: bool
    sellable: bool
    estimated_slippage_pct: float
    social_mentions_15m: int
    social_velocity_pct: float
    trusted_kol_mentions: int
    price_change_5m_pct: float
    price_change_1h_pct: float
    pool_age_minutes: int
    social_data_available: bool = True
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class AgentReport:
    agent: str
    score: float
    confidence: str
    reasons: List[str]
    vetoes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommanderDecision:
    mint: str
    symbol: str
    score: float
    status: str
    reasons: List[str]
    vetoes: List[str]
    reports: Dict[str, AgentReport]
    paper_position_usd: float = 0.0
