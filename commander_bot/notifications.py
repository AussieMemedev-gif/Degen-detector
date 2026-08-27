import json
import urllib.parse
import urllib.request
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
