from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .config import Settings
from .storage import Ledger


PriceLookup = Callable[[str], float]


def live_price(mint: str) -> float:
    from .live_data import best_pair
    return float(best_pair(mint).get("priceUsd") or 0)


def process_wallet_events(
    settings: Settings, ledger: Ledger, events: List[Dict[str, Any]],
    price_lookup: Optional[PriceLookup] = None,
) -> List[str]:
    if ledger.get_state("paper_copy_enabled", "OFF") != "ON":
        return []
    lookup = price_lookup or live_price
    messages: List[str] = []
    for event in events:
        action = str(event.get("action", ""))
        if action not in {"BUY / TOKEN IN", "SELL / TOKEN OUT"}:
            continue
        mint = str(event["mint"])
        try:
            price = lookup(mint)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            continue
        if price <= 0:
            continue
        now = datetime.now(timezone.utc)
        if action == "BUY / TOKEN IN":
            if len(ledger.open_paper_positions()) >= settings.paper_copy_max_open_positions:
                continue
            opened = ledger.open_paper_position(
                str(event["wallet_address"]), str(event["wallet_label"]), mint, price,
                settings.paper_position_usd, str(event["signature"]), now,
            )
            if opened:
                messages.append(
                    "🧪 PAPER COPY — OPENED\n"
                    f"Source: {event['wallet_label']}\nToken: {mint}\n"
                    f"Entry: ${price:.10f}\nPaper size: ${settings.paper_position_usd:.2f}\n\n"
                    "Simulation only. No wallet transaction was submitted."
                )
        else:
            pnls = ledger.close_paper_positions(
                str(event["wallet_address"]), mint, price, str(event["signature"]), now,
            )
            for pnl in pnls:
                messages.append(
                    "🧪 PAPER COPY — CLOSED\n"
                    f"Source: {event['wallet_label']}\nToken: {mint}\n"
                    f"Exit: ${price:.10f}\nRealized paper P&L: {pnl:+.2f} USD\n\n"
                    "Simulation only. No wallet transaction was submitted."
                )
    return messages


def paper_status_message(settings: Settings, ledger: Ledger) -> str:
    enabled = ledger.get_state("paper_copy_enabled", "OFF")
    return (
        "🧪 PAPER COPY TRADING\n"
        f"Status: {enabled}\n"
        f"Position size: ${settings.paper_position_usd:.2f}\n"
        f"Maximum open positions: {settings.paper_copy_max_open_positions}\n\n"
        "Tracked-wallet BUY/SELL signals are mirrored only in the simulator.\n"
        "No wallet connection, private key, or real transaction is used."
    )


def portfolio_message(ledger: Ledger) -> str:
    positions = ledger.open_paper_positions()
    closed, pnl, wins, losses = ledger.paper_totals()
    lines = [
        "🧪 PAPER PORTFOLIO",
        f"Open positions: {len(positions)}",
        f"Closed positions: {closed}",
        f"Realized P&L: {pnl:+.2f} USD",
        f"Wins/Losses: {wins}/{losses}",
    ]
    if positions:
        lines.append("\nOPEN")
        for label, mint, _, entry, _, size in positions[:10]:
            lines.append(f"• {label} | {mint[:6]}…{mint[-4:]} | ${size:.2f} @ ${entry:.10f}")
    lines.append("\nExperimental paper results; fees and execution latency are not fully modelled.")
    return "\n".join(lines)


def trader_rankings_message(ledger: Ledger) -> str:
    rows = ledger.trader_performance()
    if not rows:
        return "🏆 PAPER TRADER RANKINGS\n\nNo completed simulated trades yet."
    lines = ["🏆 PAPER TRADER RANKINGS", ""]
    for index, (label, address, trades, wins, pnl) in enumerate(rows[:20], start=1):
        win_rate = (wins / trades * 100) if trades else 0
        lines.append(f"{index}. {label} ({address[:5]}…{address[-4:]})")
        lines.append(f"   Trades: {trades} | Win rate: {win_rate:.0f}% | P&L: {pnl:+.2f} USD")
    lines.append("\nRanked only from Degen Detector's paper observations—not proof of future performance.")
    return "\n".join(lines)
