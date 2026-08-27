import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from .models import CommanderDecision


def format_alert(decision: CommanderDecision, display_name: str = "Degen Detector") -> str:
    lines = [f"💎 {display_name.upper()} — {decision.status}", f"{decision.symbol} | {decision.mint}", f"Commander Score: {decision.score:.1f}/100"]
    if decision.paper_position_usd:
        lines.append(f"Paper position: ${decision.paper_position_usd:.2f}")
    if decision.vetoes:
        lines.append("Vetoes: " + "; ".join(decision.vetoes))
    lines.extend(decision.reasons)
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
    ]}


def send_control_menu(token: str, chat_id: str, message: str) -> None:
    telegram_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "reply_markup": control_keyboard(),
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
