# Degen Detector MVP

**Detect the send before the trend.**

A safety-first Solana hidden-gem detector and paper-trading command centre. Four specialist agents score each candidate and The Commander applies hard vetoes before creating a paper-trade recommendation.

## Included

- Social Alpha, On-Chain Scout, Chart Trader, and Risk/Security agents
- Weighted Commander decisions with non-negotiable safety vetoes
- SQLite audit ledger for signals, decisions, and paper positions
- Telegram alert delivery (optional)
- Demo feed so the full pipeline works before API keys are added
- Automated tests
- Live execution deliberately disabled

## Quick start

```bash
python -m commander_bot.main --once
python -m unittest discover -s commander_bot/tests -v
```

Copy `.env.example` to `.env` and add credentials later. Never paste wallet private keys into Telegram or source code.

## Safety gates

A candidate is rejected if liquidity is below the configured floor, holder concentration is excessive, mint/freeze authority remains active, sellability fails, or estimated slippage is excessive. `LIVE_TRADING_ENABLED` is ignored by this MVP: only paper trades can be created.

## Next integrations

1. Helius webhook/RPC adapter for token and wallet events.
2. DEX market-data adapter for liquidity, volume, price, and pool age.
3. X and Reddit adapters within approved API terms.
4. Telegram bot commands and approval buttons.
5. Historical replay and forward paper-trading evaluation.
