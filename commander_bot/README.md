# Degen Detector MVP

**Detect the send before the trend.**

A safety-first Solana hidden-gem detector and paper-trading command centre. Four specialist agents score each candidate and The Commander applies hard vetoes before creating a paper-trade recommendation.

## Included

- Social Alpha, On-Chain Scout, Chart Trader, and Risk/Security agents
- Weighted Commander decisions with non-negotiable safety vetoes
- SQLite audit ledger for signals, decisions, and paper positions
- Telegram alert delivery (optional)
- Telegram control menu with Manual, Automatic, Scan Once, Stop, Status, and Emergency Stop
- Demo feed so the full pipeline works before API keys are added
- Automated tests
- Live execution deliberately disabled
- Optional Live Data V3 scanner using DEX Screener discovery and Helius on-chain checks
- Live Data V4 Telegram reports with price, liquidity, volume, pool age, holder concentration, authority warnings, decision reasons, and direct chart links
- Automatic V5 peak-window scanning with intervals, score filtering, duplicate-alert cooldowns, status reporting, and Emergency Stop enforcement
- Telegram V6 settings menu for changing interval, peak window, score floor, and repeat cooldown without GitHub or Railway
- Live Hot Token Leaderboard that excludes unsafe, dumping, and severely overextended candidates
- Read-only Wallet/KOL Tracker with Telegram-managed addresses and new token movement signals
- Opt-in V9 Paper Copy simulator with fixed-size positions, a paper portfolio, and experimental tracked-trader rankings

## Quick start

```bash
python -m commander_bot.main --once
python -m commander_bot.main --controls
python -m unittest discover -s commander_bot/tests -v
```

Set the environment variables shown in `.env.example` in the hosting dashboard. Never paste bot tokens or wallet private keys into Telegram or source code. Send `/start` to the bot after the control service starts.

The control buttons operate the safe paper pipeline. `Automatic` runs scans only inside its configured local-time peak window, applies an alert score floor, and suppresses repeated alerts. Manual sessions declare a configurable expiry. Emergency Stop blocks manual and automatic scanning.

Paper Copy starts disabled. Enable it from **Wallet / KOL Tracker → Paper Copy Trading** or with `/paperon`. New observed BUY signals open simulated fixed-size positions and corresponding SELL signals close them. `/portfolio` shows paper positions and `/traders` ranks only completed simulations. It never submits a transaction and never asks for a private key.

Set `HELIUS_API_KEY` and `LIVE_DATA_ENABLED=true` to make **Scan Now** use real Solana candidates. Live mode remains paper-only. DEX Screener provides pair liquidity, transactions, volume, price and pool age; Helius verifies mint/freeze authority, supply and top-account concentration. Social/KOL feeds and reliable sell simulation are not yet connected, and reports state that limitation.

## Safety gates

A candidate is rejected if liquidity is below the configured floor, holder concentration is excessive, mint/freeze authority remains active, sellability fails, or estimated slippage is excessive. `LIVE_TRADING_ENABLED` is ignored by this MVP: only paper trades can be created.

## Next integrations

1. Helius webhook/RPC adapter for token and wallet events.
2. DEX market-data adapter for liquidity, volume, price, and pool age.
3. X and Reddit adapters within approved API terms.
4. Railway peak-time scheduled jobs.
5. Historical replay and forward paper-trading evaluation.
