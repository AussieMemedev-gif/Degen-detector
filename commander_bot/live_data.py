import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from .agents import ChartTraderAgent, OnChainScoutAgent, RiskSecurityAgent, SocialAlphaAgent
from .commander import ChiefCommander
from .config import Settings
from .models import CommanderDecision, TokenSnapshot
from .notifications import format_live_alert, send_research_result, send_telegram
from .storage import Ledger


DEX_PROFILES_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
DEX_PAIRS_URL = "https://api.dexscreener.com/token-pairs/v1/solana/{}"


def _get_json(url: str, timeout: int = 15) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "DegenDetector/0.3"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _post_json(url: str, payload: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "DegenDetector/0.3"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def discover_mints(limit: int) -> List[str]:
    profiles = _get_json(DEX_PROFILES_URL)
    seen: set[str] = set()
    result: List[str] = []
    for profile in profiles if isinstance(profiles, list) else []:
        mint = str(profile.get("tokenAddress", ""))
        if profile.get("chainId") == "solana" and mint and mint not in seen:
            seen.add(mint)
            result.append(mint)
            if len(result) >= limit:
                break
    return result


def best_pair(mint: str) -> Dict[str, Any]:
    pairs = _get_json(DEX_PAIRS_URL.format(urllib.parse.quote(mint)))
    solana_pairs = [pair for pair in pairs if pair.get("chainId") == "solana"] if isinstance(pairs, list) else []
    if not solana_pairs:
        raise ValueError("no active Solana pair")
    base_pairs = [
        pair for pair in solana_pairs
        if str((pair.get("baseToken") or {}).get("address") or "") == mint
    ]
    candidates = base_pairs or solana_pairs
    return max(candidates, key=lambda pair: float((pair.get("liquidity") or {}).get("usd") or 0))


def helius_rpc(api_key: str, method: str, params: List[Any]) -> Dict[str, Any]:
    if not api_key:
        raise ValueError("HELIUS_API_KEY is required for live scans")
    url = "https://mainnet.helius-rpc.com/?api-key=" + urllib.parse.quote(api_key)
    response = _post_json(url, {"jsonrpc": "2.0", "id": "degen-detector", "method": method, "params": params})
    if "error" in response:
        raise RuntimeError(str(response["error"].get("message", "Helius RPC error")))
    return response.get("result") or {}


def onchain_risk(mint: str, api_key: str) -> Dict[str, Any]:
    account = helius_rpc(api_key, "getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    parsed = (((account.get("value") or {}).get("data") or {}).get("parsed") or {}).get("info") or {}
    supply_result = helius_rpc(api_key, "getTokenSupply", [mint])
    largest_result = helius_rpc(api_key, "getTokenLargestAccounts", [mint])
    supply = int((supply_result.get("value") or {}).get("amount") or 0)
    largest = largest_result.get("value") or []
    top10_amount = sum(int(item.get("amount") or 0) for item in largest[:10])
    if not parsed or supply <= 0:
        raise ValueError("incomplete on-chain mint or supply data")
    return {
        "mint_authority_active": parsed.get("mintAuthority") is not None,
        "freeze_authority_active": parsed.get("freezeAuthority") is not None,
        "top10_holder_pct": (top10_amount / supply) * 100,
    }


def snapshot_from_pair(mint: str, pair: Dict[str, Any], risk: Dict[str, Any]) -> TokenSnapshot:
    txns = pair.get("txns") or {}
    m5_txns = txns.get("m5") or {}
    buys = int(m5_txns.get("buys") or 0)
    sells = int(m5_txns.get("sells") or 0)
    volume = pair.get("volume") or {}
    m5_volume = float(volume.get("m5") or 0)
    h1_volume = float(volume.get("h1") or 0)
    expected_m5 = h1_volume / 12 if h1_volume else 0
    acceleration = ((m5_volume / expected_m5) - 1) * 100 if expected_m5 else 0
    liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
    created_ms = int(pair.get("pairCreatedAt") or int(time.time() * 1000))
    price_change = pair.get("priceChange") or {}
    base = pair.get("baseToken") or {}
    return TokenSnapshot(
        mint=mint,
        symbol=str(base.get("symbol") or "UNKNOWN"),
        price_usd=float(pair.get("priceUsd") or 0),
        liquidity_usd=liquidity,
        volume_5m_usd=m5_volume,
        volume_change_pct=acceleration,
        buys_5m=buys,
        buy_sell_ratio=buys / max(sells, 1),
        top10_holder_pct=float(risk["top10_holder_pct"]),
        mint_authority_active=bool(risk["mint_authority_active"]),
        freeze_authority_active=bool(risk["freeze_authority_active"]),
        sellable=liquidity > 0 and sells > 0,
        estimated_slippage_pct=(25 / max(liquidity, 1)) * 200,
        social_mentions_15m=0,
        social_velocity_pct=0,
        trusted_kol_mentions=0,
        price_change_5m_pct=float(price_change.get("m5") or 0),
        price_change_1h_pct=float(price_change.get("h1") or 0),
        pool_age_minutes=max(0, int((time.time() * 1000 - created_ms) / 60_000)),
        social_data_available=False,
        chart_url=str(pair.get("url") or ""),
        dex_id=str(pair.get("dexId") or "unknown"),
        observed_at=datetime.now(timezone.utc),
    )


def analyse_candidates_with_diagnostics(
    settings: Settings, mints: Iterable[str]
) -> tuple[List[tuple[TokenSnapshot, CommanderDecision]], Dict[str, int]]:
    agents = [SocialAlphaAgent(), OnChainScoutAgent(), ChartTraderAgent(), RiskSecurityAgent(settings)]
    commander = ChiefCommander(agents, settings)
    results: List[tuple[TokenSnapshot, CommanderDecision]] = []
    diagnostics: Dict[str, int] = {}
    for mint in mints:
        try:
            pair = best_pair(mint)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError):
            diagnostics["DEX/pair data unavailable"] = diagnostics.get("DEX/pair data unavailable", 0) + 1
            continue
        try:
            risk = onchain_risk(mint, settings.helius_api_key)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError):
            diagnostics["On-chain verification incomplete"] = diagnostics.get("On-chain verification incomplete", 0) + 1
            continue
        try:
            snapshot = snapshot_from_pair(mint, pair, risk)
            results.append((snapshot, commander.decide(snapshot)))
        except (OSError, ValueError, RuntimeError, KeyError, TypeError):
            diagnostics["Invalid market data"] = diagnostics.get("Invalid market data", 0) + 1
            continue
    return sorted(results, key=lambda item: item[1].score, reverse=True), diagnostics


def analyse_candidates(settings: Settings, mints: Iterable[str]) -> List[tuple[TokenSnapshot, CommanderDecision]]:
    results, _ = analyse_candidates_with_diagnostics(settings, mints)
    return results


def hot_score(snapshot: TokenSnapshot, decision: CommanderDecision) -> float:
    """Rank liquid, safe tokens that are holding momentum instead of actively dumping."""
    if decision.status == "REJECTED" or decision.vetoes:
        return -1
    if snapshot.price_change_5m_pct < -8 or snapshot.price_change_1h_pct < -20:
        return -1
    if snapshot.price_change_5m_pct > 150 or snapshot.price_change_1h_pct > 400:
        return -1
    score = decision.score
    score += 6 if -2 <= snapshot.price_change_5m_pct <= 25 else 0
    score += 6 if 0 <= snapshot.price_change_1h_pct <= 100 else 0
    score += min(max(snapshot.buy_sell_ratio - 1, 0) * 4, 8)
    score += 4 if snapshot.liquidity_usd >= 50_000 else 0
    if snapshot.price_change_5m_pct > 75 or snapshot.price_change_1h_pct > 250:
        score -= 12
    return round(max(0, min(100, score)), 1)


def format_hot_leaderboard(results: List[tuple[TokenSnapshot, CommanderDecision]], limit: int = 10) -> str:
    ranked = sorted(
        ((hot_score(snapshot, decision), snapshot, decision) for snapshot, decision in results),
        key=lambda item: item[0],
        reverse=True,
    )
    ranked = [item for item in ranked if item[0] >= 0][:limit]
    if not ranked:
        return (
            "🔥 HOT TOKEN LEADERBOARD\n\n"
            "No tokens currently meet the safety and holding-strength checks.\n"
            "Live data / paper only."
        )
    lines = ["🔥 HOT TOKEN LEADERBOARD", "Live data / paper only", ""]
    for index, (rank_score, snapshot, decision) in enumerate(ranked, start=1):
        state = "💎 HOLDING" if snapshot.price_change_5m_pct >= -2 else "👀 WATCH"
        lines.extend([
            f"{index}. {snapshot.symbol} — {rank_score:.1f}/100 {state}",
            f"Commander {decision.score:.1f} | 5m {snapshot.price_change_5m_pct:+.1f}% | 1h {snapshot.price_change_1h_pct:+.1f}%",
            f"Liquidity ${snapshot.liquidity_usd:,.0f} | Buy/Sell {snapshot.buy_sell_ratio:.2f}",
            f"Mint: {snapshot.mint}",
            f"Chart: {snapshot.chart_url}" if snapshot.chart_url else "",
            "",
        ])
    lines.append("⚠️ Rankings can change quickly. No wallet access; not financial advice.")
    return "\n".join(line for line in lines if line != "" or lines[-1] == line)


def build_hot_leaderboard(settings: Settings) -> str:
    if not settings.live_data_enabled:
        return "🔥 Leaderboard unavailable: live data is disabled."
    results = analyse_candidates(settings, discover_mints(settings.live_candidate_limit))
    ledger = Ledger(settings.database_path)
    for snapshot, decision in results:
        ledger.record(snapshot, decision)
    return format_hot_leaderboard(results, max(1, min(10, settings.scan_result_limit)))


def visible_scan_results(
    results: List[tuple[TokenSnapshot, CommanderDecision]], limit: int
) -> List[tuple[TokenSnapshot, CommanderDecision]]:
    """Return only non-vetoed research candidates, ordered by Commander score."""
    safe = [
        (snapshot, decision)
        for snapshot, decision in results
        if decision.status != "REJECTED" and not decision.vetoes
    ]
    return safe[:max(1, min(10, limit))]


def research_class(decision: CommanderDecision, qualified_score: float) -> str:
    if decision.status == "REJECTED" or decision.vetoes:
        return "REJECTED INVESTIGATION"
    if decision.score >= qualified_score:
        return "QUALIFIED RESEARCH"
    return "WATCHLIST RESEARCH"


def investigated_scan_results(
    results: List[tuple[TokenSnapshot, CommanderDecision]], limit: int, qualified_score: float
) -> List[tuple[TokenSnapshot, CommanderDecision]]:
    """Rank green first, amber second and rejected investigations last."""
    priority = {
        "QUALIFIED RESEARCH": 0,
        "WATCHLIST RESEARCH": 1,
        "REJECTED INVESTIGATION": 2,
    }
    ranked = sorted(
        results,
        key=lambda item: (priority[research_class(item[1], qualified_score)], -item[1].score),
    )
    return ranked[:max(1, min(10, limit))]


def format_scan_summary(
    displayed: List[tuple[TokenSnapshot, CommanderDecision]],
    all_results: List[tuple[TokenSnapshot, CommanderDecision]],
    analysed_count: int,
    discovered_count: int,
    qualified_score: float,
    result_limit: int,
    diagnostics: Dict[str, int] | None = None,
) -> str:
    classes = [research_class(decision, qualified_score) for _, decision in all_results]
    qualified = classes.count("QUALIFIED RESEARCH")
    watchlist = classes.count("WATCHLIST RESEARCH")
    rejected = classes.count("REJECTED INVESTIGATION")
    incomplete = max(0, discovered_count - analysed_count)
    lines = [
        "🔎 DEGEN DETECTOR RESEARCH SCAN\n"
        f"Analysed successfully: {analysed_count}/{discovered_count}\n"
        f"Qualified research: {qualified} ({qualified_score:.0f}+)\n"
        f"Watchlist research: {watchlist}\n"
        f"Rejected investigations: {rejected}\n"
        f"Incomplete data: {incomplete}\n"
        f"Showing: {len(displayed)} of up to {max(1, min(10, result_limit))}\n"
    ]
    if diagnostics:
        lines.append("\nINCOMPLETE-DATA BREAKDOWN\n")
        lines.extend(f"• {reason}: {count}\n" for reason, count in sorted(diagnostics.items()))
    veto_counts: Dict[str, int] = {}
    for _, decision in all_results:
        for veto in decision.vetoes:
            veto_counts[veto] = veto_counts.get(veto, 0) + 1
    if veto_counts:
        lines.append("\nREJECTION BREAKDOWN\n")
        lines.extend(f"• {reason}: {count}\n" for reason, count in sorted(veto_counts.items()))
    lines.append("\n🟢 Qualified | 🟡 Watchlist | 🔴 Rejected investigation\n")
    lines.append(
        "Rejected tokens cannot create automatic paper positions; manual Practice Trade remains fake-money education."
    )
    return "".join(lines)


def run_live_scan(settings: Settings) -> str:
    mints = discover_mints(max(1, settings.live_candidate_limit))
    results, diagnostics = analyse_candidates_with_diagnostics(settings, mints)
    if not results:
        message = "🔎 Live scan completed: no candidates passed data-integrity checks. No paper trade created."
        send_telegram(settings.telegram_token, settings.telegram_chat_id, message)
        return message
    ledger = Ledger(settings.database_path)
    for snapshot, decision in results:
        ledger.record(snapshot, decision)
    displayed = investigated_scan_results(results, settings.scan_result_limit, settings.scan_qualified_score)
    summary = format_scan_summary(
        displayed,
        all_results=results,
        analysed_count=len(results),
        discovered_count=len(mints),
        qualified_score=settings.scan_qualified_score,
        result_limit=settings.scan_result_limit,
        diagnostics=diagnostics,
    )
    send_telegram(settings.telegram_token, settings.telegram_chat_id, summary)
    for index, (snapshot, decision) in enumerate(displayed, start=1):
        label = research_class(decision, settings.scan_qualified_score)
        message = (
            f"📌 RESULT {index}/{len(displayed)} — {label}\n"
            + format_live_alert(snapshot, decision, settings.bot_display_name)
        )
        send_research_result(
            settings.telegram_token,
            settings.telegram_chat_id,
            message,
            snapshot.mint,
            snapshot.chart_url,
        )
    return summary


def run_automatic_scan(settings: Settings, now: datetime | None = None) -> str:
    """Run a quiet, filtered paper-only scan for the automatic scheduler."""
    now = now or datetime.now(timezone.utc)
    if not settings.live_data_enabled:
        return "Automatic scan skipped: live data is disabled."
    results = analyse_candidates(settings, discover_mints(settings.live_candidate_limit))
    if not results:
        return "Automatic scan completed: no valid candidates."
    ledger = Ledger(settings.database_path)
    for snapshot, decision in results:
        ledger.record(snapshot, decision)
    best_snapshot, best_decision = results[0]
    if best_decision.status == "REJECTED" or best_decision.score < settings.auto_alert_min_score:
        return f"Automatic scan completed: best score {best_decision.score:.1f}; no alert."
    if ledger.recently_alerted(best_snapshot.mint, settings.auto_duplicate_cooldown_minutes, now):
        return f"Automatic scan completed: repeat alert suppressed for {best_snapshot.symbol}."
    message = "🕒 AUTOMATIC PEAK-TIME ALERT\n" + format_live_alert(
        best_snapshot, best_decision, settings.bot_display_name
    )
    send_telegram(settings.telegram_token, settings.telegram_chat_id, message)
    group_id = str(settings.telegram_alert_group_id).strip()
    if group_id and group_id != str(settings.telegram_chat_id):
        send_telegram(settings.telegram_token, group_id, message)
    ledger.record_alert(best_snapshot.mint, now)
    return f"Automatic alert sent for {best_snapshot.symbol} ({best_decision.score:.1f}/100)."
