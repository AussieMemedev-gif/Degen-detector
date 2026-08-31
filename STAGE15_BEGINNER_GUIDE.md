# Degen Detector Stage 15 — Beginner Guide

## Stage 15.2 dual-chain support

- Network selector for **Solana** and **Robinhood Chain** CA searches.
- Solana accepts base58 token mints; Robinhood Chain accepts ERC-20 `0x` addresses.
- Robinhood Chain uses chain ID `4663`, ETH gas, DEX Screener market data and Uniswap wallet routes.
- Practice Quick Buy automatically uses SOL sizing on Solana and ETH sizing on Robinhood Chain.
- A separate Robinhood Early Radar ranks indexed young pools by liquidity, hourly volume and
  buy/sell activity. It is labelled market-first and never claims unverified contract safety.
- Real transactions remain owner-only and require approval in a self-custodial wallet.

## Stage 15.1 additions

- **Search Contract Address** on the home dashboard accepts a complete Solana CA and opens the
  token in Practice mode by default.
- Quick paper buys, quick percentage exits, manual SOL/USD buys and manual percentage sells.
- Adjustable 1–95% practice stop loss with a 30-second monitoring cycle; enter 0 to remove it.
- Owner-only self-custodial real-trade routes through Jupiter. Every real transaction must be
  reviewed and approved in the owner's wallet; the bot never stores a private key.
- **Early Mooner Radar** ranks young tokens using live holder count, top-holder concentration,
  liquidity, volume acceleration, buy/sell pressure, token age and existing safety vetoes.

## What changed

Stage 15 turns the Telegram chat into a guided dashboard. The home screen now shows only the
five journeys a user needs: Scan, Discover, Practice, Trackers and Learn. Status remains visible,
while scheduling, settings and emergency controls are separated into the owner's Admin area.

No feature in this release submits a blockchain transaction. Practice Trade and Paper Copy use
simulated funds. Wallet tracking reads public addresses only.

## The home dashboard

### 🔎 Scan for Tokens

This is the recommended starting point. Tap **Start New Scan** and wait for the ranked reports.
The bot may return up to ten investigated candidates:

- 🟢 **Qualified** passed the hard safety gates and reached the configured research score.
- 🟡 **Watch** passed the hard vetoes but has weaker evidence. Wait and research further.
- 🔴 **Rejected** failed at least one hard safety check. The report explains the failure.

For each result, read the liquidity, pool age, holder concentration, authorities, sell evidence,
slippage and price movement. Open the live chart before deciding whether to practise.

### 🚀 Discover

Browse Pump.fun, BONK, Raydium, Meteora and Jupiter candidates. **Qualified 75+** filters for the
strongest current research scores. The sniper and bundle percentages are screening estimates,
not forensic proof. Discovery is for making a watchlist; use a full Scan before practising.

### 🎮 Practice

Practice with isolated fake funds:

1. Run a scan and choose a token.
2. Tap **Trade with Fake Money** on that exact result.
3. Review the selected token and open its live chart.
4. Choose a fixed fake SOL amount or use Custom Buy.
5. Open Wallet to confirm the simulated position.
6. Exit 25%, 50%, 75% or 100% and review P&L and History.

Practice fills model fees and slippage. They are not real orders and do not predict the price at
which a real trade would execute.

### 🔍 Search Contract Address

Tap the button, paste the complete Solana CA, and wait for live pair validation. The selected token
opens in Practice mode. Quick Buy uses the fixed SOL buttons; Manual Buy accepts values such as
`0.75 SOL` or `$250`; Manual Sell accepts a percentage from 1 to 100.

Use **Set / Adjust Stop Loss** after opening a practice position. A 10% stop means the bot attempts
a full simulated exit when the live quote reaches 10% below the average entry. Monitoring is not
instant and can be delayed by API outages, rate limits or service restarts.

The owner can open **Admin → Owner Real Trade** after selecting a CA. Buy, Sell and real stop-order
buttons open the official Jupiter interface. Verify the mint and quote, then approve—or reject—the
transaction in the connected wallet.

### 🌙 Early Mooner Radar

Open Discover and select Early Mooner Radar. It favours younger pools with accelerating volume,
more buys than sells, usable liquidity, broader holder distribution and no hard safety vetoes. A
high score is an early-research lead, not a prediction or guarantee.

### 👛 Trackers

Track public Solana wallet activity. To add an address, send:

`/track PUBLIC_ADDRESS Label`

Use **Tracked Wallets** to review the list and **Check Signals** to look for new movements. Paper
Copy is optional and simulates future tracked BUY/SELL signals. Never paste a seed phrase or
private key. The bot never needs one.

### 🎓 Learn

This area explains score colours, the safety checklist, and the Practice walkthrough. It is the
best first stop for someone who has never traded or used a Telegram bot.

## Owner Admin area

- **Manual Session** enables the owner's temporary manual scan mode.
- **Stop Scans** returns scanning to OFF.
- **Automatic Scanning** asks for confirmation, then follows the configured time window and interval.
- **Scan Settings** controls interval, peak window, minimum alert score and repeat cooldown.
- **Emergency Stop** asks for confirmation and blocks scans and wallet checks immediately.

Testers cannot see or call these controls. All tester data and fake-money accounts remain isolated.

## Five rules for using the bot effectively

1. Treat every score as research, never as a promise of profit.
2. Prefer green results, but independently inspect liquidity, holders, authorities and the chart.
3. Do not chase a vertical candle; wait for price and volume to stabilise.
4. Practise first and keep any eventual real-world risk small enough to lose completely.
5. Never share a seed phrase, private key, password or recovery code with any bot or person.

## Useful commands

- `/start` or `/menu` — open the dashboard
- `/scan` — run a research scan
- `/learn` — open the learning centre
- `/status` — show account and bot status
- `/help` — show full instructions
- `/cancel` — cancel a pending custom paper order

## Important limitations

Degen Detector currently focuses on Solana research and simulation. Social/KOL feeds are not yet
fully connected, sellability checks are evidence-based rather than guarantees, launch-forensics
figures can be estimates, and meme tokens can lose most or all of their value very quickly.
