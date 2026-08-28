import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from .models import CommanderDecision, TokenSnapshot


def format_alert(decision: CommanderDecision, display_name: str = "Degen Detector") -> str:
    lines = [f"💎 {display_name.upper()} — {decision.status}", f"{decision.symbol} | {decision.mint}", f"Commander Score: {decision.score:.1f}/100"]
    if decision.paper_position_usd:
        lines.append(f"Paper position: ${decision.paper_position_usd:.2f}")
    if decision.vetoes:
        lines.append("Vetoes: " + "; ".join(decision.vetoes))
    lines.extend(decision.reasons)
    return "\n".join(lines)


def _usd(value: float) -> str:
    if 0 < value < 0.01:
        return f"${value:.10f}".rstrip("0")
    return f"${value:,.2f}"


def _age(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 1_440:
        return f"{minutes // 60}h {minutes % 60}m"
    return f"{minutes // 1_440}d {(minutes % 1_440) // 60}h"


def format_live_alert(token: TokenSnapshot, decision: CommanderDecision, display_name: str = "Degen Detector") -> str:
    status_icon = {"PAPER_BUY_APPROVED": "🟢", "WATCHLIST": "🟡", "REJECTED": "🔴"}.get(decision.status, "⚪")
    lines = [
        "🌐 LIVE DATA / PAPER ONLY",
        f"{status_icon} {display_name.upper()} — {decision.status}",
        f"🪙 {token.symbol}",
        f"Mint: {token.mint}",
        "",
        f"🎯 Commander: {decision.score:.1f}/100",
        f"💵 Price: {_usd(token.price_usd)}",
        f"💧 Liquidity: {_usd(token.liquidity_usd)}",
        f"📊 Volume 5m: {_usd(token.volume_5m_usd)}",
        f"🧾 Buys 5m: {token.buys_5m} | Buy/Sell: {token.buy_sell_ratio:.2f}",
        f"📈 Price: {token.price_change_5m_pct:+.1f}% (5m) | {token.price_change_1h_pct:+.1f}% (1h)",
        f"⏳ Pool age: {_age(token.pool_age_minutes)} | DEX: {token.dex_id}",
        "",
        "🛡️ SAFETY",
        f"Top-10 holders: {token.top10_holder_pct:.1f}%",
        f"Mint authority: {'ACTIVE ⚠️' if token.mint_authority_active else 'Revoked ✅'}",
        f"Freeze authority: {'ACTIVE ⚠️' if token.freeze_authority_active else 'Revoked ✅'}",
        f"Observed sells: {'Yes ✅' if token.sellable else 'No ⚠️'}",
        f"Estimated slippage: {token.estimated_slippage_pct:.2f}%",
        "",
        "🤖 SPECIALISTS",
        f"Social: {decision.reports['social'].score:.1f}/100 (feed not connected)",
        f"On-chain: {decision.reports['onchain'].score:.1f}/100",
        f"Chart: {decision.reports['chart'].score:.1f}/100",
        f"Risk: {decision.reports['risk'].score:.1f}/100",
    ]
    if decision.paper_position_usd:
        lines.append(f"\n🧪 Paper position: ${decision.paper_position_usd:.2f}")
    if decision.vetoes:
        lines.append("\n⛔ REJECTION REASONS")
        lines.extend(f"• {veto}" for veto in decision.vetoes)
    elif decision.status == "WATCHLIST":
        lines.append("\n👀 Below the approval score; watchlist only.")
    lines.append("\n⚠️ No wallet access. Not financial advice.")
    if token.chart_url:
        lines.append(f"🔗 Chart: {token.chart_url}")
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, message: str) -> None:
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        json.loads(response.read())


def telegram_request(token: str, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    encoded = urllib.parse.urlencode({
        key: json.dumps(value) if isinstance(value, (dict, list)) else value
        for key, value in payload.items()
    }).encode()
    request = urllib.request.Request(url, data=encoded, method="POST")
    with urllib.request.urlopen(request, timeout=35) as response:
        result = json.loads(response.read())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method} request failed")
    return result


def control_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [
            {"text": "⚡ Scan Now", "callback_data": "scan_once"},
            {"text": "📊 Status", "callback_data": "status"},
        ],
        [
            {"text": "▶️ Manual On", "callback_data": "manual_on"},
            {"text": "⏹️ Stop", "callback_data": "stop"},
        ],
        [
            {"text": "🕒 Automatic", "callback_data": "automatic"},
            {"text": "🚨 Emergency Stop", "callback_data": "emergency_stop"},
        ],
        [{"text": "🔥 Hot Token Leaderboard", "callback_data": "leaderboard"}],
        [{"text": "👛 Wallet / KOL Tracker", "callback_data": "wallet_tracker"}],
        [{"text": "⚙️ Settings", "callback_data": "settings"}],
    ]}


def settings_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [{"text": "SCAN INTERVAL", "callback_data": "noop"}],
        [
            {"text": "3m", "callback_data": "interval_3"},
            {"text": "5m", "callback_data": "interval_5"},
            {"text": "10m", "callback_data": "interval_10"},
            {"text": "15m", "callback_data": "interval_15"},
            {"text": "30m", "callback_data": "interval_30"},
        ],
        [{"text": "PEAK WINDOW", "callback_data": "noop"}],
        [
            {"text": "24/7", "callback_data": "window_0_0"},
            {"text": "18–02", "callback_data": "window_18_2"},
            {"text": "20–04", "callback_data": "window_20_4"},
            {"text": "22–06", "callback_data": "window_22_6"},
        ],
        [{"text": "ALERT SCORE", "callback_data": "noop"}],
        [
            {"text": "50+", "callback_data": "score_50"},
            {"text": "60+", "callback_data": "score_60"},
            {"text": "70+", "callback_data": "score_70"},
            {"text": "80+", "callback_data": "score_80"},
        ],
        [{"text": "REPEAT COOLDOWN", "callback_data": "noop"}],
        [
            {"text": "1h", "callback_data": "cooldown_60"},
            {"text": "3h", "callback_data": "cooldown_180"},
            {"text": "6h", "callback_data": "cooldown_360"},
        ],
        [{"text": "⬅️ Main Menu", "callback_data": "main_menu"}],
    ]}


def wallet_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [
            {"text": "📋 Tracked Wallets", "callback_data": "wallet_list"},
            {"text": "📡 Check Signals", "callback_data": "wallet_signals"},
        ],
        [{"text": "➕ How to Add / Remove", "callback_data": "wallet_help"}],
        [{"text": "⬅️ Main Menu", "callback_data": "main_menu"}],
    ]}


def send_control_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": control_keyboard(),
    })


def send_settings_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": settings_keyboard(),
    })


def send_wallet_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": wallet_keyboard(),
    })


def get_updates(token: str, offset: Optional[int], timeout: int) -> List[Dict[str, Any]]:
    payload: Dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
    if offset is not None:
        payload["offset"] = offset
    return telegram_request(token, "getUpdates", payload).get("result", [])


def answer_callback(token: str, callback_id: str, text: str = "") -> None:
    telegram_request(token, "answerCallbackQuery", {
        "callback_query_id": callback_id,
        "text": text,
    })
