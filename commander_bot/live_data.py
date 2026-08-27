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
from .notifications import format_alert, send_telegram
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
    return max(solana_pairs, key=lambda pair: float((pair.get("liquidity") or {}).get("usd") or 0))


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
        observed_at=datetime.now(timezone.utc),
    )


def analyse_candidates(settings: Settings, mints: Iterable[str]) -> List[tuple[TokenSnapshot, CommanderDecision]]:
    agents = [SocialAlphaAgent(), OnChainScoutAgent(), ChartTraderAgent(), RiskSecurityAgent(settings)]
    commander = ChiefCommander(agents, settings)
    results: List[tuple[TokenSnapshot, CommanderDecision]] = []
    for mint in mints:
        try:
            snapshot = snapshot_from_pair(mint, best_pair(mint), onchain_risk(mint, settings.helius_api_key))
            results.append((snapshot, commander.decide(snapshot)))
        except (OSError, ValueError, RuntimeError, KeyError, TypeError):
            continue
    return sorted(results, key=lambda item: item[1].score, reverse=True)


def run_live_scan(settings: Settings) -> str:
    results = analyse_candidates(settings, discover_mints(settings.live_candidate_limit))
    if not results:
        message = "🔎 Live scan completed: no candidates passed data-integrity checks. No paper trade created."
        send_telegram(settings.telegram_token, settings.telegram_chat_id, message)
        return message
    ledger = Ledger(settings.database_path)
    for snapshot, decision in results:
        ledger.record(snapshot, decision)
    best_snapshot, best_decision = results[0]
    message = "🌐 LIVE DATA / PAPER ONLY\n" + format_alert(best_decision, settings.bot_display_name)
    send_telegram(settings.telegram_token, settings.telegram_chat_id, message)
    return message
