"""Per-user live-price paper terminal. It never signs or submits a transaction."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .config import Settings
from .storage import Ledger


WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"
WRAPPED_ETH_MINT = "ethereum:0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
PriceLookup = Callable[[str], float]


def split_asset(asset: str) -> tuple[str, str]:
    if ":" in asset:
        chain, address = asset.split(":", 1)
        return chain, address
    return "solana", asset


def asset_id(chain: str, address: str) -> str:
    return f"robinhood:{address.lower()}" if chain == "robinhood" else address


def live_price(mint: str) -> float:
    from .live_data import best_pair
    price = float(best_pair(mint).get("priceUsd") or 0)
    if price <= 0:
        raise ValueError("live price unavailable")
    return price


def live_token_profile(mint: str) -> tuple[str, float, str]:
    from .live_data import best_pair
    pair = best_pair(mint)
    price = float(pair.get("priceUsd") or 0)
    symbol = str((pair.get("baseToken") or {}).get("symbol") or mint[:6]).upper()[:16]
    return symbol, price, str(pair.get("url") or "")


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _price(value: float) -> str:
    return f"${value:.12f}".rstrip("0").rstrip(".") if value < 0.01 else f"${value:,.6f}"


def _liquidation_value(quantity: float, market_price: float, settings: Settings) -> float:
    after_slippage = quantity * market_price * (1 - max(0, settings.practice_slippage_pct) / 100)
    return after_slippage * (1 - max(0, settings.practice_fee_pct) / 100)


class PracticeTrading:
    def __init__(self, settings: Settings, ledger: Ledger):
        self.settings = settings
        self.ledger = ledger
        self.ledger.ensure_practice_account(max(100, settings.practice_starting_balance_usd))

    @property
    def selected_mint(self) -> str:
        return self.ledger.get_state("practice_selected_mint", "")

    @property
    def selected_symbol(self) -> str:
        return self.ledger.get_state("practice_selected_symbol", "")

    @property
    def selected_chart(self) -> str:
        return self.ledger.get_state("practice_selected_chart", "")

    @property
    def selected_chain(self) -> str:
        return split_asset(self.selected_mint)[0] if self.selected_mint else "solana"

    @property
    def selected_address(self) -> str:
        return split_asset(self.selected_mint)[1] if self.selected_mint else ""

    def select_token(self, mint: str, symbol: str = "") -> str:
        detected_symbol, price, chart = live_token_profile(mint)
        clean_symbol = (symbol or detected_symbol).upper()[:16]
        self.ledger.set_state("practice_selected_mint", mint)
        self.ledger.set_state("practice_selected_symbol", clean_symbol)
        self.ledger.set_state("practice_selected_chart", chart)
        chain, address = split_asset(mint)
        return f"✅ {clean_symbol} selected on {chain.title()} at {_price(price)}.\nCA: {address}\nNo real transaction was submitted."

    def hourly_remaining(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        used = self.ledger.practice_hourly_buys(now)
        return max(0.0, self.settings.practice_hourly_buy_limit_usd - used)

    def terminal_message(self, price_lookup: PriceLookup | None = None) -> str:
        lookup = price_lookup or live_price
        cash = self.ledger.practice_cash()
        remaining = self.hourly_remaining()
        lines = [
            "🎮 DEGEN DETECTOR PAPER TERMINAL",
            "LIVE PRICES / FAKE MONEY / ZERO WALLET ACCESS",
            "",
            f"💵 Virtual cash: {_money(cash)}",
            f"⏱️ Hourly buy power: {_money(remaining)} / {_money(self.settings.practice_hourly_buy_limit_usd)}",
            f"⚙️ Simulated fee: {self.settings.practice_fee_pct:.2f}% | Slippage: {self.settings.practice_slippage_pct:.2f}%",
        ]
        mint = self.selected_mint
        if not mint:
            lines.extend([
                "",
                "No token selected.",
                "Choose Trade with Fake Money beneath a research result or use:",
                "/trade TOKEN_MINT SYMBOL",
            ])
        else:
            try:
                token_price = lookup(mint)
                native = WRAPPED_ETH_MINT if self.selected_chain == "robinhood" else WRAPPED_SOL_MINT
                sol_price = lookup(native)
                lines.extend([
                    "",
                    f"🎯 Selected: {self.selected_symbol or mint[:6]}",
                    f"Price: {_price(token_price)}",
                    f"{'ETH' if self.selected_chain == 'robinhood' else 'SOL'} reference: {_money(sol_price)}",
                    f"Network: {split_asset(mint)[0].title()}",
                    f"CA: {split_asset(mint)[1]}",
                ])
                position = self.ledger.practice_position(mint)
                if position:
                    value = _liquidation_value(float(position[2]), token_price, self.settings)
                    pnl = value - float(position[4])
                    pnl_pct = (pnl / float(position[4]) * 100) if position[4] else 0
                    lines.extend([
                        f"Position: {_money(value)}",
                        f"Average entry: {_price(float(position[3]))}",
                        f"Unrealized P&L: {pnl:+,.2f} USD ({pnl_pct:+.1f}%)",
                    ])
                    stop = self.stop_loss_percent(mint)
                    if stop:
                        trigger = float(position[3]) * (1 - stop / 100)
                        lines.append(f"Stop loss: -{stop:g}% (trigger {_price(trigger)})")
                else:
                    lines.append("Position: None")
            except (OSError, RuntimeError, ValueError, KeyError, TypeError):
                lines.append("\n⚠️ Selected token price is temporarily unavailable.")
        lines.append("\nSimulation only. Buttons never create a Solana transaction.")
        return "\n".join(lines)

    def stop_loss_percent(self, mint: str | None = None) -> float:
        mint = mint or self.selected_mint
        if not mint:
            return 0.0
        try:
            return float(self.ledger.get_state(f"practice_stop:{mint}", "0"))
        except ValueError:
            return 0.0

    def set_stop_loss(self, percent: float) -> str:
        mint = self.selected_mint
        position = self.ledger.practice_position(mint) if mint else None
        if not position:
            return "⛔ Buy the selected token with fake money before setting a stop loss."
        if percent == 0:
            self.ledger.set_state(f"practice_stop:{mint}", "0")
            return "✅ Practice stop loss removed."
        if percent < 1 or percent > 95:
            return "Enter a stop loss from 1% to 95%, or 0 to remove it."
        self.ledger.set_state(f"practice_stop:{mint}", f"{percent:g}")
        trigger = float(position[3]) * (1 - percent / 100)
        return f"🛡️ Practice stop loss set to -{percent:g}% at approximately {_price(trigger)}."

    def check_stop_losses(self, price_lookup: PriceLookup | None = None) -> list[str]:
        lookup = price_lookup or live_price
        messages: list[str] = []
        selected_before = (self.selected_mint, self.selected_symbol, self.selected_chart)
        for mint, symbol, _, entry, *_ in self.ledger.practice_positions():
            percent = self.stop_loss_percent(mint)
            if not percent:
                continue
            try:
                current = lookup(mint)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError):
                continue
            if current <= float(entry) * (1 - percent / 100):
                self.ledger.set_state("practice_selected_mint", mint)
                self.ledger.set_state("practice_selected_symbol", symbol)
                result = self.sell_percent(100, token_price=current)
                self.ledger.set_state(f"practice_stop:{mint}", "0")
                messages.append(f"🛡️ PRACTICE STOP LOSS TRIGGERED\n{result}")
        self.ledger.set_state("practice_selected_mint", selected_before[0])
        self.ledger.set_state("practice_selected_symbol", selected_before[1])
        self.ledger.set_state("practice_selected_chart", selected_before[2])
        return messages

    def buy_sol(
        self, sol_amount: float, token_price: float | None = None, sol_price: float | None = None,
        now: datetime | None = None,
    ) -> str:
        mint = self.selected_mint
        if not mint:
            return "Select a token before using a paper buy."
        now = now or datetime.now(timezone.utc)
        try:
            token_price = token_price or live_price(mint)
            reference = WRAPPED_ETH_MINT if self.selected_chain == "robinhood" else WRAPPED_SOL_MINT
            sol_price = sol_price or live_price(reference)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            return "⚠️ Live price unavailable. No paper order was created."
        gross = sol_amount * sol_price
        fee = gross * max(0, self.settings.practice_fee_pct) / 100
        total = gross + fee
        if total > self.hourly_remaining(now) + 1e-9:
            return f"⛔ Hourly paper-buy limit exceeded. Remaining: {_money(self.hourly_remaining(now))}."
        if total > self.ledger.practice_cash() + 1e-9:
            return f"⛔ Insufficient virtual cash. Available: {_money(self.ledger.practice_cash())}."
        fill = token_price * (1 + max(0, self.settings.practice_slippage_pct) / 100)
        quantity = gross / fill
        self.ledger.practice_buy(
            mint, self.selected_symbol or mint[:6], quantity, fill, gross, fee, sol_amount, now,
        )
        return (
            "🎯 PAPER BUY FILLED\n"
            f"Token: {self.selected_symbol or mint[:6]}\n"
            f"Size: {sol_amount:g} {'ETH' if self.selected_chain == 'robinhood' else 'SOL'} ({_money(gross)})\n"
            f"Fill: {_price(fill)}\nFee: {_money(fee)}\n"
            f"Tokens: {quantity:,.6f}\n\nNo wallet transaction was submitted."
        )

    def buy_usd(
        self, usd_amount: float, token_price: float | None = None, sol_price: float | None = None,
        now: datetime | None = None,
    ) -> str:
        if usd_amount <= 0:
            return "Enter a paper-buy amount greater than zero."
        try:
            reference = WRAPPED_ETH_MINT if self.selected_chain == "robinhood" else WRAPPED_SOL_MINT
            reference_sol_price = sol_price or live_price(reference)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            return "⚠️ SOL reference price unavailable. No paper order was created."
        return self.buy_sol(
            usd_amount / reference_sol_price,
            token_price=token_price,
            sol_price=reference_sol_price,
            now=now,
        )

    def sell_percent(
        self, percent: int, token_price: float | None = None, now: datetime | None = None,
    ) -> str:
        mint = self.selected_mint
        position = self.ledger.practice_position(mint) if mint else None
        if not position:
            return "⛔ No selected paper position is available to sell."
        now = now or datetime.now(timezone.utc)
        try:
            token_price = token_price or live_price(mint)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            return "⚠️ Live price unavailable. No paper order was created."
        bounded = max(1, min(100, percent))
        quantity = float(position[2]) * bounded / 100
        fill = token_price * (1 - max(0, self.settings.practice_slippage_pct) / 100)
        gross = quantity * fill
        fee = gross * max(0, self.settings.practice_fee_pct) / 100
        cost_removed = float(position[3]) * quantity
        pnl = (gross - fee) - cost_removed
        self.ledger.practice_sell(
            mint, str(position[1]), quantity, fill, gross, fee, pnl, now,
        )
        return (
            "⚡ PAPER SELL FILLED\n"
            f"Token: {position[1]}\nSold: {bounded}%\n"
            f"Fill: {_price(fill)}\nProceeds: {_money(gross - fee)}\n"
            f"Realized P&L: {pnl:+,.2f} USD\n\nNo wallet transaction was submitted."
        )

    def wallet_message(self, price_lookup: PriceLookup | None = None) -> str:
        lookup = price_lookup or live_price
        positions = self.ledger.practice_positions()
        cash = self.ledger.practice_cash()
        lines = ["👛 PRACTICE WALLET", f"Virtual cash: {_money(cash)}", f"Open tokens: {len(positions)}"]
        market_value = 0.0
        if positions:
            lines.append("\nTOKEN HOLDINGS")
        for mint, symbol, quantity, entry, cost, *_ in positions[:20]:
            try:
                current = lookup(mint)
                value = _liquidation_value(quantity, current, self.settings)
                pnl = value - cost
                pnl_pct = (pnl / cost * 100) if cost else 0
                market_value += value
                lines.append(
                    f"• {symbol} | Value {_money(value)} | P&L {pnl:+,.2f} ({pnl_pct:+.1f}%)\n"
                    f"  Avg {_price(entry)} | Now {_price(current)} | {mint[:6]}…{mint[-4:]}"
                )
            except (OSError, RuntimeError, ValueError, KeyError, TypeError):
                lines.append(f"• {symbol} | Price unavailable | {mint[:6]}…{mint[-4:]}")
        equity = cash + market_value
        lines.insert(2, f"Account equity: {_money(equity)}")
        lines.append("\nFake funds only. Values move with live market prices.")
        return "\n".join(lines)

    def history_message(self) -> str:
        rows = self.ledger.practice_history(20)
        if not rows:
            return "📜 PRACTICE HISTORY\n\nNo paper trades yet."
        lines = ["📜 PRACTICE TRADE HISTORY", "Latest 20 fills", ""]
        for occurred, symbol, mint, side, quantity, fill, gross, fee, pnl, sol_size in rows:
            extra = f" | {sol_size:g} SOL" if side == "BUY" else f" | P&L {pnl:+.2f}"
            lines.append(
                f"• {side} {symbol} | {_money(gross)}{extra}\n"
                f"  Fill {_price(fill)} | Fee {_money(fee)} | {occurred[:16]} UTC\n"
                f"  {mint[:6]}…{mint[-4:]}"
            )
        return "\n".join(lines)

    def profile_message(self) -> str:
        account = self.ledger.practice_account()
        cash, starting, created = account if account else (0.0, 0.0, "")
        trades, buys, sells = self.ledger.practice_trade_counts()
        completed, wins, realized, fees = self.ledger.practice_statistics()
        win_rate = wins / completed * 100 if completed else 0
        return (
            "👤 MY PRACTICE PROFILE\n"
            "Account: Isolated training wallet\n"
            f"Member since: {created[:10] or 'Today'}\n"
            f"Starting balance: {_money(float(starting))}\n"
            f"Virtual cash: {_money(float(cash))}\n"
            f"Hourly buying power left: {_money(self.hourly_remaining())}\n"
            f"Open tokens: {len(self.ledger.practice_positions())}\n"
            f"Orders: {trades} ({buys} buys / {sells} sells)\n"
            f"Realized P&L: {realized:+,.2f} USD\n"
            f"Win rate: {win_rate:.1f}%\n"
            f"Sell fees modelled: {_money(fees)}\n\n"
            "This profile belongs only to this Telegram user. Fake funds only."
        )

    def pnl_message(self, price_lookup: PriceLookup | None = None) -> str:
        lookup = price_lookup or live_price
        sells, wins, realized, sell_fees = self.ledger.practice_statistics()
        unrealized = 0.0
        for mint, _, quantity, _, cost, *_ in self.ledger.practice_positions():
            try:
                unrealized += _liquidation_value(quantity, lookup(mint), self.settings) - cost
            except (OSError, RuntimeError, ValueError, KeyError, TypeError):
                continue
        win_rate = wins / sells * 100 if sells else 0
        total = realized + unrealized
        return (
            "📊 ALL-TIME PRACTICE P&L\n"
            f"Realized: {realized:+,.2f} USD\n"
            f"Unrealized: {unrealized:+,.2f} USD\n"
            f"Total P&L: {total:+,.2f} USD\n"
            f"Completed sells: {sells}\nWin rate: {win_rate:.1f}%\n"
            f"Sell fees paid: {_money(sell_fees)}\n\n"
            "Practice results do not predict real trading performance."
        )

    def top_gains_message(self) -> str:
        rows = self.ledger.practice_top_gains(10)
        if not rows:
            return "🏆 TOP 10 PRACTICE GAINS\n\nNo profitable paper sells yet."
        lines = ["🏆 TOP 10 PRACTICE GAINS", ""]
        for index, (occurred, symbol, mint, pnl, gross) in enumerate(rows, start=1):
            lines.append(
                f"{index}. {symbol} | {pnl:+,.2f} USD | Sale {_money(gross)}\n"
                f"   {mint[:6]}…{mint[-4:]} | {occurred[:10]}"
            )
        return "\n".join(lines)
