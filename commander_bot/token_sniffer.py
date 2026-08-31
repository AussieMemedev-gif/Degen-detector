"""Read-only Solana contract and market screening for user-submitted mints."""

from dataclasses import dataclass

from .agents import (
    ChartTraderAgent, DeveloperWalletAgent, NarrativeResearchAgent,
    OnChainScoutAgent, RiskSecurityAgent, SocialAlphaAgent,
)
from .commander import ChiefCommander
from .config import Settings
from .live_data import best_pair, developer_wallet_trace, onchain_risk, snapshot_from_pair


@dataclass(frozen=True)
class SnifferResult:
    message: str
    mint: str
    chart_url: str = ""


def _usd(value: float) -> str:
    if 0 < value < 0.01:
        return f"${value:.12f}".rstrip("0").rstrip(".")
    return f"${value:,.2f}"


def sniff_token(settings: Settings, mint: str) -> SnifferResult:
    try:
        pair = best_pair(mint)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        return SnifferResult(
            "🧪 TOKEN SNIFFER — REJECT / UNVERIFIED\n\n"
            f"Mint: {mint}\n"
            "Score: Unavailable\n"
            "Reason: No active Solana market pair or reliable price/liquidity data was found.\n\n"
            "Do not treat an unverified contract as safe. Research only; no wallet access.",
            mint,
        )
    chart = str(pair.get("url") or "")
    base = pair.get("baseToken") or {}
    symbol = str(base.get("symbol") or "UNKNOWN").upper()
    market_cap = float(pair.get("marketCap") or pair.get("fdv") or 0)
    liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
    price = float(pair.get("priceUsd") or 0)
    try:
        risk = onchain_risk(mint, settings.helius_api_key)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        return SnifferResult(
            "🧪 TOKEN SNIFFER — REJECT / INCOMPLETE\n\n"
            f"Token: {symbol}\nMint: {mint}\n"
            "Score: Unavailable\n"
            f"Price: {_usd(price)}\nMarket cap/FDV: {_usd(market_cap) if market_cap else 'Unavailable'}\n"
            f"Liquidity: {_usd(liquidity)}\n"
            "Reason: On-chain authority, supply or holder verification could not be completed.\n\n"
            "Incomplete verification is never labelled safe. Research only; no wallet access.",
            mint,
            chart,
        )
    try:
        risk["developer"] = developer_wallet_trace(mint, settings.helius_api_key)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        risk["developer"] = {"wallet": "", "confidence": "unavailable", "activity_count": 0}
    snapshot = snapshot_from_pair(mint, pair, risk)
    agents = [
        SocialAlphaAgent(), OnChainScoutAgent(), ChartTraderAgent(), RiskSecurityAgent(settings),
        DeveloperWalletAgent(), NarrativeResearchAgent(),
    ]
    decision = ChiefCommander(agents, settings).decide(snapshot)
    if decision.vetoes:
        signal = "🔴 REJECT"
    elif decision.score >= settings.scan_qualified_score:
        signal = "🦍 APE RESEARCH"
    else:
        signal = "🟡 WATCHLIST"
    lines = [
        f"🧪 TOKEN SNIFFER — {signal}",
        f"Token: {snapshot.symbol}",
        f"Mint: {mint}",
        f"Degen score: {decision.score:.1f}/100",
        "",
        f"Price: {_usd(snapshot.price_usd)}",
        f"Market cap/FDV: {_usd(market_cap) if market_cap else 'Unavailable'}",
        f"Liquidity: {_usd(snapshot.liquidity_usd)}",
        f"Volume 5m: {_usd(snapshot.volume_5m_usd)}",
        f"Price change: {snapshot.price_change_5m_pct:+.1f}% (5m) | {snapshot.price_change_1h_pct:+.1f}% (1h)",
        f"Buy/Sell: {snapshot.buy_sell_ratio:.2f}",
        "",
        "CONTRACT & HOLDER CHECKS",
        f"Top-10 holders: {snapshot.top10_holder_pct:.1f}%",
        f"Mint authority: {'ACTIVE ⚠️' if snapshot.mint_authority_active else 'Revoked ✅'}",
        f"Freeze authority: {'ACTIVE ⚠️' if snapshot.freeze_authority_active else 'Revoked ✅'}",
        f"Observed sells: {'Yes ✅' if snapshot.sellable else 'No ⚠️'}",
        f"Estimated $25 slippage: {snapshot.estimated_slippage_pct:.2f}%",
        "",
        "STAGE 15 INTELLIGENCE",
        f"Developer trace: {decision.reports['developer'].score:.1f}/100 "
        f"({decision.reports['developer'].confidence})",
        f"Launch signer: {snapshot.developer_wallet or 'Unverified'}",
        f"Narrative links: {snapshot.social_links_count} social | {snapshot.website_links_count} website",
        "External social sentiment: Not connected",
    ]
    if decision.vetoes:
        lines.extend(["", "REJECTION REASONS"])
        lines.extend(f"• {reason}" for reason in decision.vetoes)
    elif signal.endswith("WATCHLIST"):
        lines.extend(["", f"Below the {settings.scan_qualified_score:.0f}+ Ape research threshold."])
    else:
        lines.extend(["", "Passed the current hard vetoes and research-score threshold."])
    lines.extend([
        "",
        "Classification is research, not an instruction or guarantee to buy.",
        "Fake-money trading only. No wallet access.",
    ])
    return SnifferResult("\n".join(lines), mint, chart)
