# Degen Detector Stage 16 — Master Bot Guide

## What this overhaul fixes

The previous Automatic Mode scheduled research scans and alerts; it did not manage a trading
strategy. Stage 16 keeps that research scheduler, then adds a separate **Master Practice
Auto-Trader** that can open, monitor and close simulated positions. It still cannot access a
wallet, sign a transaction or trade real funds.

The dashboard has been reorganised around the questions a beginner actually asks:

1. Is this token safe enough to investigate?
2. What are the best meme candidates now?
3. Why did the strategy trade or skip it?
4. Is the paper strategy making or losing fake money?
5. What does each trading term mean?

## New home dashboard

### 🔎 Check a Token

Paste a complete Solana or Robinhood Chain contract address. Solana receives the fuller safety
analysis when Live Data and Helius are configured. The report gives one of three verdicts:

- **🟢 Paper Entry Ready** — every Master entry rule passed. This is permission for a fake-money
  test, not a prediction.
- **🟡 Watch / Skip** — the token may be interesting, but the evidence or timing is incomplete.
- **🔴 Avoid** — a hard safety rule failed. The Master system cannot auto-enter it.

Under the verdict, read **Good Signs**, **Risks / Missing Evidence**, Commander Score and Data
Confidence. Data Confidence measures how much required evidence was available; it is not the
probability of profit.

### 🚀 Meme Radar

- **Best Meme Candidates** runs the full ranked Solana investigation.
- **Trending Now** favours usable liquidity and controlled momentum rather than a token that is
  already dumping or extremely extended.
- **Early Movers** looks for younger pools with volume acceleration, buy pressure and broader
  distribution.
- **New Launches** groups discoveries by supported launch source.
- **Wallet / KOL** monitors public Solana wallets and can simulate copy signals.
- **Source Coverage** shows exactly which feeds are available, missing or staged.

Stage 16 can use live DEX discovery and Solana on-chain checks. With approved credentials, it can
also query official X recent search and YouTube recent-video search. TikTok, Instagram, Facebook
and Reddit settings are staged for later approved adapters. Telegram's Bot API does not provide a
global search of every public channel, so the bot does not pretend it can see all Telegram trends.

### 🤖 Practice Auto-Trader

This is the strategy control and explanation area.

- **Status** shows whether automatic paper entries are on or off and displays current limits.
- **Enable Paper Auto** is owner-only. It also enables scheduled research scanning.
- **Entry & Exit Rules** explains the decision logic.
- **Why It Traded / Skipped** shows the most recent audited decisions.
- **Strategy Performance** shows open and closed simulations, win rate, average win/loss and total
  fake P&L.

An entry requires all of the following:

- no Commander safety veto;
- observed sell activity and acceptable estimated slippage;
- enough liquidity;
- Commander score at or above the configured Master threshold;
- enough real data coverage;
- constructive, but not abnormally one-sided, buy/sell pressure; and
- rising momentum that is not already an extreme vertical pump.

Position size is reduced when score or data confidence is lower and capped to a small fraction of
available liquidity. The strategy refuses duplicate open positions and stops opening new ones at
the configured maximum. If realised fake losses reach the daily loss limit, automatic paper
entries switch off and require a manual review.

Every simulated entry receives:

- a hard stop loss;
- first and second profit checkpoints; and
- a trailing exit that becomes active after the first checkpoint.

Open Master positions are repriced during scheduled scans. A simulated position closes at the
hard stop, second target, or trailing stop. API outages can delay checks, so this is forward-test
research rather than an execution guarantee.

### 💼 My Paper Portfolio

Use **Strategy Performance** for the Master system's automatic simulations. Use **Balance &
Positions**, **Profit / Loss**, **Trade History**, and **Best Trades** for your personal manual
practice account. These are deliberately separated so a manual experiment cannot be mistaken for
the automatic strategy's result.

### 📚 Learn & Safety

Start with **Quick Start**, then read **Good vs Bad Trade** and the glossary. The essential rule is
simple: several independent green signs can support a setup, but one serious red safety failure
can block it. Never use a score as a promise of profit.

### 🧠 Master System Lab

This owner-only area contains data health, strategy performance, paper-auto controls, discovery
settings, scan schedule and Emergency Stop. The future funded-wallet executor is shown as locked.

## How to use the bot effectively

### First-time setup

1. Open the private Telegram chat and send `/start`.
2. Open **Learn & Safety → Quick Start**.
3. Open **Master System Lab → Data Health** and confirm DEX and Solana checks are available.
4. Leave the Master Auto-Trader off while testing individual reports.
5. Use **Check a Token** with a known contract address, then compare its verdict with the live chart.

### Safe daily workflow

1. Open **Meme Radar → Best Meme Candidates**.
2. Ignore any red result. For amber results, wait for better evidence.
3. For a green candidate, read both Good Signs and Risks / Missing Evidence.
4. Check liquidity, sell evidence, holder concentration, authorities and whether the price has
   already gone vertical.
5. Use fake money only. Review simulated results in **My Paper Portfolio**.
6. At the end of the session, open **Why It Traded / Skipped** and **Strategy Performance**. A high
   win rate alone is not enough; total P&L, average win/loss and drawdowns matter too.

### Starting the automatic paper test

1. From the owner account, open **Practice Auto-Trader → Entry & Exit Rules**.
2. Confirm the configured stop, targets, maximum positions and daily fake-loss limit suit the test.
3. Tap **Enable Paper Auto**.
4. Open **Master System Lab → Scan Schedule** and choose the interval and peak-time window.
5. Let it run without changing rules after every result. A useful forward test needs many different
   market conditions.
6. Review every pause or skip before re-enabling it. Do not optimise only around winning examples.

### Emergency procedure

Open **Master System Lab → Emergency Stop** and confirm. This blocks research scans and wallet
checks. Paper Auto can also be disabled from its own dashboard. No real wallet is connected in
this release.

## What must happen before real-money automation

Do not add a funded wallet merely because a short paper run looks profitable. At minimum, require
a meaningful sample of forward-tested paper trades, positive expectancy after realistic fees and
slippage, maximum-drawdown limits, independent key-management and code-security reviews, an
owner-only arming step, immutable order logs, provider health monitoring, a tested kill switch,
and legal/regulatory review for the intended users and locations.

## Commands

- `/start` or `/menu` — open the home dashboard
- `/scan` — run a research scan
- `/learn` — open beginner learning
- `/status` — show system status
- `/help` — show full help
- `/cancel` — cancel a pending address or manual practice-order input

## Reality check

No bot can collect literally all information, predict meme markets precisely, or guarantee a
profitable entry. APIs have coverage limits, outages and rate limits; social activity can be
manipulated; and a token can fail after passing earlier checks. Stage 16's professional improvement
is not a promise of certainty—it is explicit evidence coverage, hard vetoes, conservative sizing,
repeatable exits, full decision logs and measurable paper performance.
