"""Risk-aware paper auto-trading and plain-English trade explanations.

This module cannot sign or submit blockchain transactions. It deliberately proves
the strategy with realistic paper entries and exits before any separate live
executor is considered.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterable

from .config import Settings
from .models import CommanderDecision, TokenSnapshot
from .storage import Ledger


@dataclass(frozen=True)
class TradePlan:
    action: str
    verdict: str
    data_confidence: float
    position_usd: float
    stop_loss_pct: float
    target_one_pct: float
    target_two_pct: float
    trailing_stop_pct: float
    good_signs: list[str]
    bad_signs: list[str]
    summary: str


def data_confidence(token: TokenSnapshot) -> float:
    score = 0.0
    if token.price_usd > 0 and token.liquidity_usd > 0:
        score += 25
    if token.volume_5m_usd >= 0 and token.buys_5m >= 0:
        score += 15
    if token.top10_holder_pct > 0:
        score += 20
    if token.sellable:
        score += 10
    if token.chart_url:
        score += 5
    if token.social_data_available:
        score += 25
    return round(min(100.0, score), 1)


def build_trade_plan(
    token: TokenSnapshot, decision: CommanderDecision, settings: Settings,
) -> TradePlan:
    confidence = data_confidence(token)
    good: list[str] = []
    bad: list[str] = []

    if decision.score >= settings.master_entry_score:
        good.append(f"Commander score is strong at {decision.score:.1f}/100")
    else:
        bad.append(f"Commander score is below the {settings.master_entry_score:.0f}+ entry rule")
    if token.liquidity_usd >= max(settings.min_liquidity_usd, 50_000):
        good.append(f"Liquidity is healthier at ${token.liquidity_usd:,.0f}")
    else:
        bad.append(f"Liquidity is thin at ${token.liquidity_usd:,.0f}")
    if 1.2 <= token.buy_sell_ratio <= 4:
        good.append(f"Buy/sell activity is constructive at {token.buy_sell_ratio:.2f}")
    elif token.buy_sell_ratio < 1.0:
        bad.append("Sellers currently outweigh buyers")
    else:
        bad.append("Buy activity is unusually one-sided and may be launch noise")
    if 0 <= token.price_change_5m_pct <= 30 and token.price_change_1h_pct <= 120:
        good.append("Momentum is rising without an extreme vertical spike")
    elif token.price_change_5m_pct < -5:
        bad.append("Short-term momentum is falling")
    else:
        bad.append("Price is extended; entering now risks chasing the pump")
    if confidence >= settings.master_min_data_confidence:
        good.append(f"Available-data confidence is {confidence:.0f}/100")
    else:
        bad.append(f"Available-data confidence is only {confidence:.0f}/100")
    if not token.social_data_available:
        bad.append("Cross-platform social evidence is not connected for this result")
    bad.extend(decision.vetoes)

    hard_block = bool(decision.vetoes) or not token.sellable
    entry_ready = (
        not hard_block
        and decision.score >= settings.master_entry_score
        and confidence >= settings.master_min_data_confidence
        and token.liquidity_usd >= settings.min_liquidity_usd
        and 1.2 <= token.buy_sell_ratio <= 4
        and -2 <= token.price_change_5m_pct <= 30
        and token.price_change_1h_pct <= 120
    )
    if hard_block:
        action, verdict = "REJECT", "🔴 AVOID"
        summary = "The safety rules blocked this setup. No automatic paper entry is allowed."
    elif entry_ready:
        action, verdict = "PAPER_BUY", "🟢 PAPER ENTRY READY"
        summary = "Safety, liquidity, timing and available evidence meet the Master Trader rules."
    else:
        action, verdict = "SKIP", "🟡 WATCH / SKIP"
        summary = "The token may be interesting, but the evidence or entry timing is not strong enough yet."

    risk_factor = max(0.20, min(1.0, decision.score / 100 * confidence / 100))
    liquid_cap = max(0.0, token.liquidity_usd * 0.0005)
    position = min(settings.paper_position_usd * risk_factor, liquid_cap)
    return TradePlan(
        action=action, verdict=verdict, data_confidence=confidence,
        position_usd=round(position if entry_ready else 0.0, 2),
        stop_loss_pct=settings.master_stop_loss_pct,
        target_one_pct=settings.master_take_profit_1_pct,
        target_two_pct=settings.master_take_profit_2_pct,
        trailing_stop_pct=settings.master_trailing_stop_pct,
        good_signs=good, bad_signs=bad, summary=summary,
    )


def format_trade_plan(token: TokenSnapshot, decision: CommanderDecision, plan: TradePlan) -> str:
    lines = [
        f"{plan.verdict} — {token.symbol}",
        f"Commander: {decision.score:.1f}/100 | Data confidence: {plan.data_confidence:.0f}/100",
        "",
        "PLAIN-ENGLISH SUMMARY",
        plan.summary,
    ]
    if plan.good_signs:
        lines.extend(["", "GOOD SIGNS", *(f"✅ {item}" for item in plan.good_signs)])
    if plan.bad_signs:
        lines.extend(["", "RISKS / MISSING EVIDENCE", *(f"⚠️ {item}" for item in plan.bad_signs)])
    if plan.action == "PAPER_BUY":
        lines.extend([
            "", "PAPER PLAN",
            f"Fake position: ${plan.position_usd:.2f}",
            f"Stop loss: -{plan.stop_loss_pct:.1f}%",
            f"Profit checkpoints: +{plan.target_one_pct:.1f}% and +{plan.target_two_pct:.1f}%",
            f"Trailing stop after first checkpoint: {plan.trailing_stop_pct:.1f}%",
        ])
    lines.extend(["", "Fake-money research only. Live funded-wallet execution is disabled."])
    return "\n".join(lines)


def process_master_candidates(
    results: Iterable[tuple[TokenSnapshot, CommanderDecision]], ledger: Ledger, settings: Settings,
) -> list[str]:
    """Audit every decision and open at most one best paper position per scan."""
    ranked = sorted(results, key=lambda item: item[1].score, reverse=True)
    plans: list[tuple[TokenSnapshot, CommanderDecision, TradePlan]] = []
    for token, decision in ranked:
        plan = build_trade_plan(token, decision, settings)
        ledger.record_master_decision(
            token.observed_at, token.mint, token.symbol, plan.action, plan.verdict,
            decision.score, plan.data_confidence, plan.good_signs + plan.bad_signs,
        )
        plans.append((token, decision, plan))
    if ledger.get_state("master_paper_auto", "OFF") != "ON":
        return []
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_pnl = ledger.master_realized_pnl_since(day_start)
    if daily_pnl <= -abs(settings.master_daily_loss_limit_usd):
        ledger.set_state("master_paper_auto", "OFF")
        return [
            "🚨 Master paper auto-trader paused: the daily fake-loss limit was reached. "
            "Review decisions and performance before manually enabling it again."
        ]
    if len(ledger.master_open_positions()) >= max(1, settings.master_max_positions):
        return ["🤖 Paper auto-trader skipped entry: maximum open positions reached."]
    for token, decision, plan in plans:
        if plan.action != "PAPER_BUY":
            continue
        simulated_price = token.price_usd * (1 + settings.practice_slippage_pct / 100)
        simulated = replace(token, price_usd=simulated_price)
        opened = ledger.open_master_position(
            simulated, plan.position_usd,
            simulated_price * (1 - plan.stop_loss_pct / 100),
            simulated_price * (1 + plan.target_one_pct / 100),
            simulated_price * (1 + plan.target_two_pct / 100),
            plan.trailing_stop_pct,
        )
        if opened:
            return [
                f"🤖 MASTER PAPER ENTRY — {token.symbol}\n"
                f"Simulated entry: ${simulated_price:.10f}\n"
                f"Fake position: ${plan.position_usd:.2f}\n"
                f"Stop: -{plan.stop_loss_pct:.1f}% | Targets: +{plan.target_one_pct:.1f}% / +{plan.target_two_pct:.1f}%\n"
                "No wallet transaction was created."
            ]
    return []


def update_master_positions(
    ledger: Ledger, prices: dict[str, float], now: datetime | None = None,
) -> list[str]:
    now = now or datetime.now(timezone.utc)
    messages: list[str] = []
    for row in ledger.master_open_positions():
        (position_id, mint, symbol, _, entry, _, high, _, _, stop, target_one,
         target_two, trailing_pct) = row
        price = float(prices.get(mint) or 0)
        if price <= 0:
            continue
        high = max(float(high), price)
        ledger.mark_master_price(position_id, price)
        exit_reason = ""
        if price <= float(stop):
            exit_reason = "hard stop loss"
        elif price >= float(target_two):
            exit_reason = "second profit target"
        elif high >= float(target_one) and price <= high * (1 - float(trailing_pct) / 100):
            exit_reason = "trailing stop after first profit checkpoint"
        if exit_reason:
            pnl = ledger.close_master_position(position_id, price, exit_reason, now)
            pct = (price / float(entry) - 1) * 100
            messages.append(
                f"🤖 MASTER PAPER EXIT — {symbol}\nReason: {exit_reason}\n"
                f"Return: {pct:+.2f}% | Fake P&L: ${pnl:+.2f}\nNo wallet transaction was created."
            )
    return messages


def source_health_message(settings: Settings) -> str:
    operational = [
        ("DEX market, liquidity and launch discovery", True),
        ("Solana on-chain safety checks", bool(settings.helius_api_key)),
        ("X recent-post trends", bool(settings.x_bearer_token)),
        ("YouTube recent-video trends", bool(settings.youtube_api_key)),
    ]
    lines = ["📡 DATA-SOURCE HEALTH", ""]
    lines.extend(f"{'✅ Available/configured' if available else '⚠️ Not configured'} — {name}" for name, available in operational)
    lines.extend([
        "🧩 Credential slot staged — TikTok Research API",
        "🧩 Credential slot staged — Instagram public content",
        "🧩 Credential slot staged — Facebook public content",
        "🧩 Credential slot staged — Reddit approved API",
        "⛔ Not claimed — global Telegram channel search (Bot API does not provide it)",
    ])
    connected = sum(1 for _, available in operational if available)
    lines.extend([
        "", f"Operational coverage: {connected}/{len(operational)} current connectors",
        "A configured key is validated when a scan runs. Missing or failed sources reduce confidence; "
        "they are never silently treated as positive evidence.",
    ])
    return "\n".join(lines)


def performance_message(ledger: Ledger) -> str:
    stats = ledger.master_performance()
    readiness = (
        "Needs more forward-tested trades before live execution."
        if stats["closed"] < 100 or stats["pnl"] <= 0
        else "Promising paper evidence; independent risk review is still required."
    )
    return (
        "📈 MASTER STRATEGY REPORT\n\n"
        f"Open paper trades: {stats['open']}\n"
        f"Closed paper trades: {stats['closed']}\n"
        f"Win rate: {stats['win_rate']:.1f}%\n"
        f"Average win: ${stats['average_win']:+.2f}\n"
        f"Average loss: ${stats['average_loss']:+.2f}\n"
        f"Total fake P&L: ${stats['pnl']:+.2f}\n\n"
        f"Verdict: {readiness}\nLive funded-wallet execution remains disabled."
    )


def recent_decisions_message(ledger: Ledger) -> str:
    rows = ledger.recent_master_decisions(10)
    if not rows:
        return "🧾 No Master Trader decisions yet. Run Meme Radar first."
    lines = ["🧾 WHY IT TRADED OR SKIPPED", ""]
    for _, symbol, action, verdict, score, confidence, _ in rows:
        lines.append(f"{symbol}: {action} — {verdict} | Score {score:.0f} | Data {confidence:.0f}")
    lines.append("\nUse Check a Token for the full good-signs and risk explanation.")
    return "\n".join(lines)
