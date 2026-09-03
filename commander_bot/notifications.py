import json
import urllib.error
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
        f"Social: {decision.reports['social'].score:.1f}/100 "
        f"({'/'.join(token.social_sources) if token.social_sources else 'no official feed evidence'})",
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
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read()).get("description", str(error))
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            detail = str(error)
        raise RuntimeError(f"Telegram {method} failed: {detail}") from error
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method} request failed")
    return result


def delete_webhook(token: str) -> None:
    """Ensure this long-polling service is not blocked by a legacy webhook."""
    telegram_request(token, "deleteWebhook", {"drop_pending_updates": False})


def set_bot_commands(token: str) -> None:
    """Keep Telegram's native command menu short and useful for beginners."""
    telegram_request(token, "setMyCommands", {"commands": [
        {"command": "start", "description": "Open the Degen Detector dashboard"},
        {"command": "scan", "description": "Run a new research scan"},
        {"command": "learn", "description": "Open the beginner learning centre"},
        {"command": "status", "description": "Show bot and account status"},
        {"command": "help", "description": "Show help and safety rules"},
    ]})


def control_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [{"text": "🔎 Check a Token", "callback_data": "ca_search"}],
        [{"text": "🚀 Meme Radar", "callback_data": "meme_radar"}],
        [{"text": "🤖 Practice Auto-Trader", "callback_data": "auto_trader_hub"}],
        [{"text": "💼 My Paper Portfolio", "callback_data": "portfolio_hub"}],
        [{"text": "👛 Wallet / KOL Tracker", "callback_data": "wallet_tracker"}],
        [{"text": "📚 Learn & Safety", "callback_data": "learn_hub"}],
        [{"text": "🧠 Master System Lab", "callback_data": "master_lab"}],
    ]}


def tester_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [{"text": "🔎 Check a Token", "callback_data": "ca_search"}],
        [{"text": "🚀 Meme Radar", "callback_data": "meme_radar"}],
        [{"text": "✨ New Launches", "callback_data": "launchpads"}],
        [{"text": "🤖 Practice Auto-Trader", "callback_data": "auto_trader_hub"}],
        [{"text": "💼 My Paper Portfolio", "callback_data": "portfolio_hub"}],
        [{"text": "👛 Wallet / KOL Tracker", "callback_data": "wallet_tracker"}],
        [{"text": "📚 Learn & Safety", "callback_data": "learn_hub"}],
    ]}


def meme_radar_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [{"text": "⭐ Best Meme Candidates", "callback_data": "scan_once"}],
        [
            {"text": "🔥 Trending Now", "callback_data": "leaderboard"},
            {"text": "🌙 Early Movers", "callback_data": "early_mooners"},
        ],
        [
            {"text": "🚀 New Launches", "callback_data": "launchpads"},
            {"text": "👛 Wallet / KOL", "callback_data": "wallet_tracker"},
        ],
        [{"text": "📡 Source Coverage", "callback_data": "source_health"}],
        [{"text": "🏠 Home", "callback_data": "main_menu"}],
    ]}


def auto_trader_keyboard(owner: bool = False) -> Dict[str, Any]:
    rows = [
        [{"text": "📊 Auto-Trader Status", "callback_data": "auto_status"}],
        [{"text": "📋 Entry & Exit Rules", "callback_data": "auto_rules"}],
        [{"text": "🧾 Why It Traded / Skipped", "callback_data": "auto_decisions"}],
        [{"text": "📈 Strategy Performance", "callback_data": "auto_performance"}],
    ]
    if owner:
        rows.insert(1, [
            {"text": "✅ Enable Paper Auto", "callback_data": "paper_auto_on"},
            {"text": "⏹ Disable", "callback_data": "paper_auto_off"},
        ])
    rows.append([{"text": "🏠 Home", "callback_data": "main_menu"}])
    return {"inline_keyboard": rows}


def portfolio_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [
            {"text": "👛 Balance & Positions", "callback_data": "practice_wallet"},
            {"text": "📊 Profit / Loss", "callback_data": "practice_pnl"},
        ],
        [
            {"text": "📜 Trade History", "callback_data": "practice_history"},
            {"text": "🏆 Best Trades", "callback_data": "practice_gains"},
        ],
        [{"text": "🎮 Manual Practice", "callback_data": "practice_dashboard"}],
        [{"text": "🏠 Home", "callback_data": "main_menu"}],
    ]}


def master_lab_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [
            {"text": "📡 Data Health", "callback_data": "source_health"},
            {"text": "📈 Performance", "callback_data": "auto_performance"},
        ],
        [{"text": "🤖 Paper Auto-Trader", "callback_data": "auto_trader_hub"}],
        [{"text": "🔎 Discovery Settings", "callback_data": "settings"}],
        [{"text": "🕒 Scan Schedule", "callback_data": "admin_hub"}],
        [{"text": "🚨 Emergency Stop", "callback_data": "emergency_ask"}],
        [{"text": "🔒 Future Live Executor — Disabled", "callback_data": "live_disabled"}],
        [{"text": "🏠 Home", "callback_data": "main_menu"}],
    ]}


def scan_hub_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [{"text": "◎ Solana Research Scan", "callback_data": "scan_once"}],
        [{"text": "🟩 Robinhood Early Radar", "callback_data": "robinhood_scan"}],
        [{"text": "❓ How Scores Work", "callback_data": "score_guide"}],
        [{"text": "⬅️ Home", "callback_data": "main_menu"}],
    ]}


def ca_chain_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [
            {"text": "◎ Solana", "callback_data": "ca_chain_solana"},
            {"text": "🟩 Robinhood", "callback_data": "ca_chain_robinhood"},
        ],
        [{"text": "⬅️ Home", "callback_data": "main_menu"}],
    ]}


def discover_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [{"text": "🌙 Early Mooner Radar", "callback_data": "early_mooners"}],
        [{"text": "🔥 Hot Token Leaderboard", "callback_data": "leaderboard"}],
        [{"text": "🚀 Launchpads & Pump.fun", "callback_data": "launchpads"}],
        [{"text": "⬅️ Home", "callback_data": "main_menu"}],
    ]}


def learn_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [{"text": "🚀 Start Here", "callback_data": "quick_start"}],
        [{"text": "🎯 Read a Trade Verdict", "callback_data": "score_guide"}],
        [{"text": "👍 Good vs Bad Trade", "callback_data": "trade_setup_guide"}],
        [{"text": "🛡️ Safety Checklist", "callback_data": "safety_guide"}],
        [{"text": "🎮 Practice Walkthrough", "callback_data": "practice_guide"}],
        [{"text": "📖 Plain-English Glossary", "callback_data": "glossary"}],
        [{"text": "📖 All Instructions", "callback_data": "help"}],
        [{"text": "⬅️ Home", "callback_data": "main_menu"}],
    ]}


def admin_keyboard(confirm: str = "") -> Dict[str, Any]:
    if confirm == "automatic":
        return {"inline_keyboard": [
            [{"text": "✅ Confirm Automatic Mode", "callback_data": "automatic_confirm"}],
            [{"text": "Cancel", "callback_data": "admin_hub"}],
        ]}
    if confirm == "emergency":
        return {"inline_keyboard": [
            [{"text": "🚨 Confirm Emergency Stop", "callback_data": "emergency_confirm"}],
            [{"text": "Cancel", "callback_data": "admin_hub"}],
        ]}
    return {"inline_keyboard": [
        [
            {"text": "▶️ Manual Session", "callback_data": "manual_on"},
            {"text": "⏹ Stop Scans", "callback_data": "stop"},
        ],
        [{"text": "🕒 Automatic Scanning", "callback_data": "automatic_ask"}],
        [{"text": "⚙️ Scan Settings", "callback_data": "settings"}],
        [{"text": "🚨 Emergency Stop", "callback_data": "emergency_ask"}],
        [{"text": "⬅️ Home", "callback_data": "main_menu"}],
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
        [{"text": "🧪 Paper Copy Trading", "callback_data": "paper_copy"}],
        [{"text": "➕ How to Add / Remove", "callback_data": "wallet_help"}],
        [{"text": "⬅️ Main Menu", "callback_data": "main_menu"}],
    ]}


def paper_copy_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [
            {"text": "✅ Enable Paper Copy", "callback_data": "paper_on"},
            {"text": "⏹️ Disable", "callback_data": "paper_off"},
        ],
        [
            {"text": "📒 Portfolio", "callback_data": "paper_portfolio"},
            {"text": "🏆 Trader Rankings", "callback_data": "paper_traders"},
        ],
        [{"text": "⬅️ Wallet Tracker", "callback_data": "wallet_tracker"}],
    ]}


def launchpad_keyboard() -> Dict[str, Any]:
    return {"inline_keyboard": [
        [{"text": "🌙 Early Mooner Radar", "callback_data": "early_mooners"}],
        [
            {"text": "🟢 PF", "callback_data": "launch_pf"},
            {"text": "🐕 BONK", "callback_data": "launch_bonk"},
        ],
        [
            {"text": "🌊 Raydium", "callback_data": "launch_raydium"},
            {"text": "☄️ Meteora", "callback_data": "launch_meteora"},
        ],
        [{"text": "🪐 Jupiter", "callback_data": "launch_jupiter"}],
        [{"text": "🔥 Qualified 75+", "callback_data": "launch_qualified"}],
        [{"text": "ℹ️ Coverage & limits", "callback_data": "launch_help"}],
        [{"text": "⬅️ Main Menu", "callback_data": "main_menu"}],
    ]}


def practice_keyboard(chart_url: str = "") -> Dict[str, Any]:
    rows: List[List[Dict[str, str]]] = [
        [{"text": "👤 My Practice Profile", "callback_data": "practice_profile"}],
        [
            {"text": "👛 Wallet", "callback_data": "practice_wallet"},
            {"text": "📜 History", "callback_data": "practice_history"},
        ],
        [
            {"text": "📊 All-Time P&L", "callback_data": "practice_pnl"},
            {"text": "🏆 Top 10 Gains", "callback_data": "practice_gains"},
        ],
        [
            {"text": "🎯 Paper Snipe", "callback_data": "practice_snipe"},
            {"text": "🔄 Refresh", "callback_data": "practice_refresh"},
        ],
        [{"text": "QUICK PAPER BUY — NATIVE SIZE", "callback_data": "noop"}],
        [
            {"text": "0.5", "callback_data": "practice_buy_0_5"},
            {"text": "1", "callback_data": "practice_buy_1"},
            {"text": "2.5", "callback_data": "practice_buy_2_5"},
            {"text": "5", "callback_data": "practice_buy_5"},
            {"text": "10", "callback_data": "practice_buy_10"},
        ],
        [{"text": "✍️ Custom Buy — SOL or USD", "callback_data": "practice_manual_buy"}],
        [{"text": "✍️ Manual Sell — Position %", "callback_data": "practice_manual_sell"}],
        [{"text": "🛡️ Set / Adjust Stop Loss", "callback_data": "practice_stop_loss"}],
        [{"text": "PAPER SELL — POSITION %", "callback_data": "noop"}],
        [
            {"text": "25%", "callback_data": "practice_sell_25"},
            {"text": "50%", "callback_data": "practice_sell_50"},
            {"text": "75%", "callback_data": "practice_sell_75"},
            {"text": "100%", "callback_data": "practice_sell_100"},
        ],
        [{"text": "⚡ INSTANT PAPER SELL", "callback_data": "practice_instant_sell"}],
    ]
    if chart_url.startswith(("https://", "http://")):
        rows.append([{"text": "📈 Open Live Chart", "url": chart_url}])
    rows.append([{"text": "⬅️ Main Menu", "callback_data": "main_menu"}])
    return {"inline_keyboard": rows}


def real_trade_keyboard(mint: str, chain: str = "solana") -> Dict[str, Any]:
    safe_mint = urllib.parse.quote(mint, safe="")
    if chain == "robinhood":
        buy_url = f"https://app.uniswap.org/swap?chain=robinhood&outputCurrency={safe_mint}"
        sell_url = f"https://app.uniswap.org/swap?chain=robinhood&inputCurrency={safe_mint}"
        stop_url = "https://app.uniswap.org/"
    else:
        buy_url = f"https://jup.ag/swap/SOL-{safe_mint}"
        sell_url = f"https://jup.ag/swap/{safe_mint}-SOL"
        stop_url = "https://jup.ag/spot"
    return {"inline_keyboard": [
        [{"text": "🟢 Open Wallet Buy", "url": buy_url}],
        [{"text": "🔴 Open Wallet Sell", "url": sell_url}],
        [{"text": "🛡️ Real Order Controls", "url": stop_url}],
        [{"text": "⬅️ Practice Terminal", "callback_data": "practice_dashboard"}],
        [{"text": "⬅️ Home", "callback_data": "main_menu"}],
    ]}


def research_result_keyboard(mint: str, chart_url: str = "") -> Dict[str, Any]:
    rows: List[List[Dict[str, str]]] = [
        [{"text": "🎮 Trade with Fake Money", "callback_data": f"practice_select:{mint}"}],
        [{"text": "👤 My Practice Profile", "callback_data": "practice_profile"}],
    ]
    if chart_url.startswith(("https://", "http://")):
        rows[0].append({"text": "📈 Live Chart", "url": chart_url})
    return {"inline_keyboard": rows}


def send_control_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": control_keyboard(),
    })


def send_tester_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": tester_keyboard(),
    })


def send_meme_radar_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id, "text": message, "reply_markup": meme_radar_keyboard(),
    })


def send_auto_trader_menu(token: str, chat_id: str, message: str, owner: bool = False) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id, "text": message, "reply_markup": auto_trader_keyboard(owner),
    })


def send_portfolio_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id, "text": message, "reply_markup": portfolio_keyboard(),
    })


def send_master_lab_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id, "text": message, "reply_markup": master_lab_keyboard(),
    })


def send_scan_hub(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id, "text": message, "reply_markup": scan_hub_keyboard(),
    })


def send_discover_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id, "text": message, "reply_markup": discover_keyboard(),
    })


def send_learn_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id, "text": message, "reply_markup": learn_keyboard(),
    })


def send_admin_menu(token: str, chat_id: str, message: str, confirm: str = "") -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id, "text": message, "reply_markup": admin_keyboard(confirm),
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


def send_paper_copy_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": paper_copy_keyboard(),
    })


def send_launchpad_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": launchpad_keyboard(),
        "disable_web_page_preview": True,
    })


def send_practice_menu(token: str, chat_id: str, message: str, chart_url: str = "") -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": practice_keyboard(chart_url),
        "disable_web_page_preview": True,
    })


def send_real_trade_menu(token: str, chat_id: str, message: str, mint: str, chain: str = "solana") -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": real_trade_keyboard(mint, chain),
        "disable_web_page_preview": True,
    })


def send_ca_chain_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id, "text": message, "reply_markup": ca_chain_keyboard(),
    })


def send_research_result(
    token: str, chat_id: str, message: str, mint: str, chart_url: str = "",
) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": research_result_keyboard(mint, chart_url),
        "disable_web_page_preview": True,
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
