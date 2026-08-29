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
- Stage 10 Solana Launchpad Hub with PF, BONK, Raydium, Meteora, Jupiter, and Qualified 75+ filters
- Direct Pump.fun links plus clearly labelled screening estimates for sniper/bundle activity
- Beta tester allowlist with server-enforced owner/tester roles and isolated tester databases
- Legacy Telegram webhook cleanup before long polling to prevent HTTP 409 conflicts
- Stage 12 ranked research scans with up to 10 safe results, qualified/watchlist counts and tester cooldowns
- Persistent-volume-ready SQLite paths so owner and tester paper data can survive redeployments
- Stage 12.1 top-ten investigated results with green/amber/red classifications and rejection breakdowns
- Stage 13 per-user Practice Trade terminal with live-priced fake-money orders, rolling hourly buying power, realistic fee/slippage modelling, isolated wallets, history, all-time P&L and top gains

## Quick start

```bash
python -m commander_bot.main --once
python -m commander_bot.main --controls
python -m unittest discover -s commander_bot/tests -v
```

Set the environment variables shown in `.env.example` in the hosting dashboard. Never paste bot tokens or wallet private keys into Telegram or source code. Send `/start` to the bot after the control service starts.

For persistent beta data on Railway, mount a volume at `/data` and set `DATABASE_PATH=/data/commander_bot.db`. Tester databases are automatically created beside the owner database. Keep the service at one replica while using SQLite. `SCAN_RESULT_LIMIT` is bounded to 1–10; `LIVE_CANDIDATE_LIMIT` should be at least 20 if the scan is expected to find up to 10 displayable results.

For beta access, keep `TELEGRAM_OWNER_ID` set to the owner's numeric Telegram user ID and put approved private-chat user IDs in `TELEGRAM_TESTER_IDS` as a comma-separated list. `TELEGRAM_CHAT_ID` remains supported as the owner-ID fallback. An unapproved user can privately send `/start` to receive their numeric ID for approval. Testers receive research, launchpad, read-only wallet tracking and isolated paper-trading tools; global scan scheduling, settings, stop controls and emergency controls remain owner-only. Interactive commands in groups are deliberately refused. Optionally send `/groupid` in a group from the owner account, then set the returned negative ID as `TELEGRAM_ALERT_GROUP_ID` to publish the same paper-only automatic research alert in that group.

The control buttons operate the safe paper pipeline. `Automatic` runs scans only inside its configured local-time peak window, applies an alert score floor, and suppresses repeated alerts. Manual sessions declare a configurable expiry. Emergency Stop blocks manual and automatic scanning.

Paper Copy starts disabled. Enable it from **Wallet / KOL Tracker → Paper Copy Trading** or with `/paperon`. New observed BUY signals open simulated fixed-size positions and corresponding SELL signals close them. `/portfolio` shows paper positions and `/traders` ranks only completed simulations. It never submits a transaction and never asks for a private key.

Open **Practice Trade** for the manual training terminal. Every user starts with an isolated virtual balance and can select a token from a research result or use `/trade TOKEN_MINT SYMBOL`. Buys use fixed 0.5/1/2.5/5/10 SOL reference sizes; exits use 25/50/75/100% or Instant Paper Sell. `PRACTICE_HOURLY_BUY_LIMIT_USD` is a rolling one-hour cap on new fake-money buys, not an hourly cash refill. Fills include configurable simulated slippage and fees. No control signs or broadcasts a blockchain transaction.

Set `HELIUS_API_KEY` and `LIVE_DATA_ENABLED=true` to make **Scan Now** use real Solana candidates. Live mode remains paper-only. DEX Screener provides pair liquidity, transactions, volume, price and pool age; Helius verifies mint/freeze authority, supply and top-account concentration. Social/KOL feeds and reliable sell simulation are not yet connected, and reports state that limitation.

Open **Launchpads / PF** from the main Telegram menu to filter current Solana discoveries by source. `Qualified 75+` uses `LAUNCHPAD_MIN_SCORE` (default 75). The initial sniper and bundle percentages are conservative screening heuristics with low confidence; they are not forensic proof. Developer lore/history is shown as unknown until creator-wallet attribution can be verified.

## Safety gates

A candidate is rejected if liquidity is below the configured floor, holder concentration is excessive, mint/freeze authority remains active, sellability fails, or estimated slippage is excessive. `LIVE_TRADING_ENABLED` is ignored by this MVP: only paper trades can be created.

## Next integrations

1. Helius webhook/RPC adapter for token and wallet events.
2. DEX market-data adapter for liquidity, volume, price, and pool age.
3. X and Reddit adapters within approved API terms.
4. Railway peak-time scheduled jobs.
5. Historical replay and forward paper-trading evaluation.
