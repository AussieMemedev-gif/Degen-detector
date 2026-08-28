"""Read-only launchpad intelligence. No signing, wallet access, or trade execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import Settings
from .live_data import analyse_candidates, discover_mints
from .models import CommanderDecision, TokenSnapshot


@dataclass(frozen=True)
class LaunchIdentity:
    key: str
    name: str
    confidence: str


PLATFORM_NAMES = {
    "pf": "Pump.fun",
    "bonk": "LetsBONK / Bonk.fun",
    "raydium": "Raydium",
    "meteora": "Meteora",
    "jupiter": "Jupiter",
}


def identify_launchpad(token: TokenSnapshot) -> LaunchIdentity:
    """Use public mint/DEX/link evidence; never present a guess as confirmed."""
    haystack = f"{token.dex_id} {token.chart_url} {token.mint}".lower()
    if token.mint.lower().endswith("pump") or "pump.fun" in haystack or "pumpswap" in haystack:
        return LaunchIdentity("pf", "Pump.fun", "high")
    if "bonk" in haystack or token.mint.lower().endswith("bonk"):
        return LaunchIdentity("bonk", "LetsBONK / Bonk.fun", "medium")
    if "meteora" in haystack:
        return LaunchIdentity("meteora", "Meteora", "high")
    if "jupiter" in haystack:
        return LaunchIdentity("jupiter", "Jupiter", "medium")
    if "raydium" in haystack:
        return LaunchIdentity("raydium", "Raydium", "high")
    return LaunchIdentity("other", token.dex_id.title() if token.dex_id else "Unknown", "low")


def _pump_link(mint: str) -> str:
    return f"https://pump.fun/coin/{mint}"


def _bundle_estimate(token: TokenSnapshot) -> tuple[float, str]:
    """Conservative concentration proxy, not forensic bundle attribution."""
    estimate = max(0.0, min(100.0, token.top10_holder_pct - 5.0))
    return round(estimate, 1), "low"


def _sniper_estimate(token: TokenSnapshot) -> tuple[float, str]:
    """Momentum/age proxy. A transaction-level analyser will replace this later."""
    age_factor = max(0.0, 1 - token.pool_age_minutes / 120)
    activity = min(1.0, token.buys_5m / 250)
    estimate = 100 * ((age_factor * 0.6) + (activity * 0.4))
    return round(max(0, min(100, estimate)), 1), "low"


def _profile(token: TokenSnapshot, decision: CommanderDecision) -> str:
    platform = identify_launchpad(token)
    bundle_pct, bundle_confidence = _bundle_estimate(token)
    sniper_pct, sniper_confidence = _sniper_estimate(token)
    links = [f"Chart: {token.chart_url}"] if token.chart_url else []
    if platform.key == "pf":
        links.insert(0, f"PF: {_pump_link(token.mint)}")
    status = "QUALIFIED" if decision.score >= 75 and decision.status != "REJECTED" else decision.status
    return "\n".join([
        f"{'🟢' if decision.score >= 75 else '🟡'} {token.symbol} — {decision.score:.1f}/100 {status}",
        f"Launch source: {platform.name} ({platform.confidence} confidence)",
        f"Mint: {token.mint}",
        f"Price ${token.price_usd:.10f} | Liquidity ${token.liquidity_usd:,.0f}",
        f"5m {token.price_change_5m_pct:+.1f}% | 1h {token.price_change_1h_pct:+.1f}% | Buy/Sell {token.buy_sell_ratio:.2f}",
        f"Top-10: {token.top10_holder_pct:.1f}% | Sells: {'observed' if token.sellable else 'not observed'}",
        f"Estimated sniped: {sniper_pct:.1f}% ({sniper_confidence} confidence; heuristic)",
        f"Estimated bundled: {bundle_pct:.1f}% ({bundle_confidence} confidence; heuristic)",
        "Lore/profile: unavailable from current public feeds",
        "Developer history: unknown — no verified creator-wallet attribution",
        *links,
    ])


def _filter(
    results: Iterable[tuple[TokenSnapshot, CommanderDecision]], platform: str, minimum: float
) -> list[tuple[TokenSnapshot, CommanderDecision]]:
    selected = []
    for token, decision in results:
        identity = identify_launchpad(token)
        if platform == "qualified":
            matches = decision.score >= minimum and decision.status != "REJECTED"
        elif platform in {"all", "launchpads"}:
            matches = True
        else:
            matches = identity.key == platform
        if matches:
            selected.append((token, decision))
    return selected


def build_launchpad_report(settings: Settings, platform: str = "all") -> str:
    if not settings.live_data_enabled:
        return "🚀 Launchpad Hub unavailable: LIVE_DATA_ENABLED is off."
    results = analyse_candidates(settings, discover_mints(settings.launchpad_candidate_limit))
    selected = _filter(results, platform, settings.launchpad_min_score)[:3]
    title = "Qualified 75+" if platform == "qualified" else PLATFORM_NAMES.get(platform, "All Solana launch sources")
    if not selected:
        return (
            f"🚀 LAUNCHPAD HUB — {title}\n\n"
            "No current candidates matched this filter and passed data-integrity checks.\n"
            "Try again later. Live data / paper only."
        )
    profiles = [f"🚀 LAUNCHPAD HUB — {title}", "LIVE DATA / PAPER ONLY"]
    profiles.extend("\n\n" + _profile(token, decision) for token, decision in selected)
    profiles.append("\n⚠️ Sniper/bundle values are screening estimates, not transaction-forensic proof. Not financial advice.")
    return "".join(profiles)


def launchpad_help(settings: Settings) -> str:
    return (
        "ℹ️ LAUNCHPAD COVERAGE\n\n"
        "Current Stage 10: Solana discovery with PF, BONK, Raydium, Meteora and Jupiter filters. "
        "The bot enriches candidates using DEX and Solana on-chain data.\n\n"
        f"Qualified threshold: {settings.launchpad_min_score:.0f}/100.\n"
        "Platform labels depend on public mint, pair and link evidence. Developer history and exact "
        "bundle attribution remain unknown unless creator/transaction evidence can be verified.\n\n"
        "Next stage: transaction-forensic creator history, followed by Ethereum/Base/BSC adapters."
    )
