# Portfolio Workbench — Design Choices & Plain-English Guide

This document explains **what we built, why we built it that way, and what every
financial term means in plain English**. You don't need any math or finance
background to read it.

---

## 1. What this app does (in one paragraph)

You tell the app which stocks you bought and sold (or import a CSV file from
your brokerage). The app then keeps score for you: what you own right now, what
it's worth, how much you've gained or lost, how risky the mix is, and what news
is moving your stocks. An AI advisor (Claude) can look at *your actual
portfolio* and explain all of it in plain English — plus run "what if"
experiments like *"what if a 2008-style crash happened to my portfolio?"* or
*"what happens to my risk if I buy 10 more shares of NVDA?"*.

> Everything is **educational, not personalized financial advice**.

---

## 2. The big design choices, and why

### 2.1 You enter *transactions*, not *holdings*

**Choice:** You record each buy and sell (ticker, shares, price, date). The app
*derives* everything else from that list.

**Why:** If you only typed in "I own 10 shares of Apple," the app could never
tell you whether you're actually up or down, or how your account grew over
time. From the transaction list we can compute your cost, your profit (both
the locked-in kind and the on-paper kind), and a full history of your account
value. A CSV importer handles bulk entry, with a **preview step** so nothing is
imported silently.

**Plain English:**
- **Transaction** — one buy or sell. "Bought 5 shares of MSFT at $400 on March 3."
- **Holding / position** — what the transactions add up to. If you bought 10
  and sold 4, your holding is 6 shares.

### 2.2 Average cost for profit math

**Choice:** We use the **average cost** method (not tax-lot accounting).

**Why:** It's what most brokerage apps show, it's easy to understand, and tax
optimization is out of scope for an educational tool.

**Plain English:**
- **Average cost** — what you paid per share, on average. Buy 1 share at $10
  and 1 at $20 → your average cost is $15.
- **Cost basis** — total money you put into a position (shares × what you paid,
  plus fees).
- **Realized profit/loss (P&L)** — money you actually locked in by selling.
  You bought at $15 average and sold at $20 → you *realized* $5/share. This
  number can't change anymore.
- **Unrealized P&L** — profit or loss "on paper" for shares you still hold.
  It moves every day with the price. You haven't actually gained or lost it
  until you sell.

### 2.3 Time-weighted returns for the performance chart

**Choice:** The account growth chart uses **time-weighted returns (TWR)**,
treating your buys and sells as "money moving in/out," not as performance.

**Why:** Without this, adding $10,000 of new money would look like your
portfolio "went up" $10,000 that day — which is misleading. TWR answers the
honest question: *"how well did my investments perform, regardless of when I
added or removed money?"*

**Plain English:** Imagine two charts: one shows the dollar value of your
account (which jumps when you deposit money), and one shows pure investment
skill (which only moves when your stocks move). TWR is the second chart.

### 2.4 Risk is computed on your portfolio *as it is today*

**Choice:** Risk numbers use your **current** mix of stocks, measured against
each stock's price history.

**Why:** "How risky is my portfolio?" means the portfolio you hold *now* — not
the one you held last year. It also means a stock you bought yesterday still
gets a fair risk assessment (we use its full price history, not just the day
you've owned it).

**Plain English glossary for the risk report:**

- **Volatility** — how bumpy the ride is. A high-volatility portfolio swings
  up and down a lot day to day; a low-volatility one moves gently. (Technically:
  the typical size of daily moves, scaled to a year.)
- **Beta** — how much your portfolio moves *when the overall market moves*.
  Beta 1.0 = you move with the market. Beta 1.5 = when the market drops 10%,
  you tend to drop about 15%. Beta 0.5 = you only feel about half of the
  market's swings.
- **Sharpe ratio** — "reward per unit of bumpiness." Higher is better: it means
  you earned more return for each unit of risk you took. Below ~0.5 is weak,
  around 1 is good, above 2 is excellent.
- **Max drawdown** — the worst peak-to-bottom fall your portfolio took. If
  your account went from $100k down to $80k before recovering, your max
  drawdown was −20%. It answers: "what's the most pain I would have felt?"
- **VaR (Value at Risk)** — a "bad day" estimate. "Daily VaR(95%) = $1,200"
  means: on 95 out of 100 days, you should lose *less* than $1,200. It's a
  guardrail number, not a worst case.
- **CVaR (Conditional VaR / expected shortfall)** — okay, but what about those
  worst 5 days out of 100? CVaR is the *average* loss on those really bad
  days. It's always at least as scary as VaR.
- **Monte Carlo VaR** — the same "bad day" estimate, but computed by simulating
  thousands of possible tomorrows on a computer and looking at the bad ones.
  (We use a fixed random seed, so the number is reproducible.)
- **Correlation** — do two stocks move together? +1 means perfectly in sync,
  0 means unrelated, −1 means they move opposite. A portfolio of stocks that
  all move together isn't really diversified, even if it holds many names.
- **Concentration / HHI** — one number for "how many eggs are in one basket."
  HHI (Herfindahl-Hirschman Index) is just the sum of each position's weight
  squared. All your money in one stock → HHI = 1.0 (maximum concentration).
  Spread evenly across 10 stocks → HHI = 0.10 (nicely spread out). The app
  translates this into plain words like "concentrated" or "well spread out."
- **Diversification** — owning things that *don't* all fail at the same time.
  The classic "don't put all your eggs in one basket."

### 2.5 Crisis scenarios use a beta-scaled approximation

**Choice:** "What if 2008 happened?" is estimated as: *market fell X% in that
crisis → your stock tends to move beta-times the market → so your stock would
fall about beta × X%*. Every result is labeled `method: beta_approximation`.

**Why (honesty):** Our offline price cache only goes back a couple of years, so
we can't replay the *actual* 2008 day-by-day prices. The beta approximation is
a respected first-order estimate, works offline and deterministically, and we
clearly label it as an estimate — never as a prediction.

**Plain English:** If history says your portfolio feels market swings 1.3×
over, and the 2008 crash took the market down 55%, the app estimates you'd
have been down roughly 1.3 × 55% ≈ 71% — then sanity-caps the number and shows
it next to your normal daily "bad day" number for scale.

Built-in scenarios: 2008 financial crisis (−55%), COVID crash 2020 (−34%),
2022 rate shock (−25%), Black Monday 1987 (−20%), and a generic 10% correction.

### 2.6 What-if trades and rebalancing

- **What-if trade** — the app clones your portfolio in memory, pretends you
  made the trade, and shows risk numbers **before vs. after**. Nothing is
  saved; it's a sandbox.
- **Rebalancing** — over time, winners grow and your mix drifts away from what
  you intended (e.g., tech becomes 70% of your account). A rebalance plan
  lists the small buys/sells that would bring you back to a target mix (like
  "equal amounts in everything"). Tiny trades under 0.5% of the portfolio are
  dropped as not worth the bother. No tax or fee optimization — it's a
  teaching tool.

### 2.7 The AI advisor can read your portfolio but never change it

**Choice:** The AI gets **7 new read-only tools** (overview, risk report, news
for your holdings, daily briefing, scenario, what-if trade, rebalance plan).
It gets **no tool that writes** — adding/deleting transactions happens only
through the regular UI/API.

**Why:** Safety and trust. An advisor that can silently edit your records is a
liability. Read-only tools also keep the repo's core invariant: all tool logic
lives once in `tools.py`, and the MCP server / mock agent / web API just
delegate to it.

### 2.8 Storage: SQLite by default, Postgres optional

**Choice:** Your data lives in a single local file (`data/portfolio.db`,
SQLite) with zero setup. If you set `DATABASE_URL`, the exact same code runs
on Postgres instead.

**Why:** The app must work the moment you clone it — no Docker, no database
install. The models use only dialect-neutral SQLAlchemy, so they run unchanged
on both engines. (The pre-existing optional Postgres module `db.py` is left
untouched, preserving its "does nothing unless DATABASE_URL is set" contract.)

### 2.9 Alerts run in a background loop; updates arrive over WebSocket

**Choice:** Alert rules ("tell me if NVDA goes above $150", "tell me if my
drawdown passes 10%") are stored in the database and checked every ~20 seconds
by a background task inside the API server. Triggered alerts are saved as
notifications and pushed instantly to the browser over a **WebSocket**, the
same channel that feeds the live ticker tape.

**Why:** A lifespan background task needs no extra infrastructure (no Celery,
no cron). WebSocket (vs. one-way SSE) gives one persistent two-way channel
shared by prices + notifications + heartbeats; the existing SSE streaming
stays for AI chat, where it fits naturally.

**Plain English:**
- **Alert rule** — a tripwire you set: price above/below X, a daily move
  bigger than X%, RSI too hot/cold, drawdown beyond X%, or unusual news volume.
- **Cooldown** — after a rule fires, it stays quiet for a while (default 4
  hours) so you don't get spammed every 20 seconds while the condition stays true.
- **RSI (Relative Strength Index)** — a 0–100 "temperature gauge" of recent
  buying vs. selling pressure. Above ~70 traders call a stock "overbought"
  (ran up fast, may cool off); below ~30 "oversold" (beaten down, may bounce).

### 2.10 Terminal-style UI

**Choice:** A Bloomberg-terminal-inspired workspace: dense panels, monospace
numerals (JetBrains Mono), a scrolling ticker tape, a status bar with a live
clock and connection dot, and a **command palette** (press `Ctrl+K`) that lets
you jump to any ticker, switch views, add a trade, or ask the AI — all from
the keyboard.

**Why:** The brief was "clean but not generic." Consumer-app clones (Robinhood
style) are everywhere; a keyboard-first pro-terminal look is distinctive *and*
genuinely faster to use once you learn `Ctrl+K`.

**Charting:** candlestick charts come from `lightweight-charts` (the canvas
library built by TradingView) because the previous SVG chart library has no
candlestick support and slows down at hundreds of points. Donut/area charts
stay on the existing library.

**Plain English:**
- **Candlestick chart** — each bar summarizes one day: where the price opened,
  closed, and the highest/lowest it touched. Green = closed higher than it
  opened; red = closed lower.
- **SMA (simple moving average)** — the average price over the last N days,
  drawn as a smooth line. The 50-day vs. 200-day comparison is a classic
  "short-term vs. long-term trend" read.
- **Equity curve** — the line chart of your whole account's value over time.

### 2.11 Everything still works offline and deterministically

**Choice:** With `USE_MOCK_DATA=1`, every feature — ledger, analytics,
scenarios, alerts — runs on synthetic, reproducible data with no network.

**Why:** This is the repo's foundational invariant. Tests and the eval harness
must produce identical numbers on every run, on any machine, with no API keys.
The mock prices are generated from a deterministic formula seeded by the
ticker name, so "AAPL" always gets the same fake history.

---

## 3. Architecture at a glance

```
frontend (React terminal UI)
   │  REST (portfolio CRUD, CSV import, charts)
   │  WebSocket (live quotes + alert notifications)
   │  SSE (AI chat streaming)
   ▼
api/server.py (FastAPI) ── background loop: check alert rules every ~20s
   ▼
src/portfolio_risk/tools.py        ← ALL tool logic lives here, once
   ├─ portfolio/ledger.py          ← pure math: holdings, cost basis, P&L, TWR
   ├─ portfolio/analytics.py       ← glue: ledger + prices → risk report
   ├─ portfolio/scenarios.py       ← crisis tests, what-if, rebalance
   ├─ portfolio/alerts.py          ← pure rule evaluation
   ├─ portfolio/db.py + store.py   ← SQLite (default) / Postgres (optional)
   ├─ risk/metrics.py              ← existing math (VaR, beta, Sharpe…) REUSED
   └─ data/market_data.py          ← live yfinance + caches / mock twin
   ▲
server/mcp_server.py (MCP stdio) — same tools exposed to Claude
agent/ — real Claude or deterministic mock agent
```

## 4. What we deliberately did NOT build (and why)

| Cut | Why |
|---|---|
| Brokerage account sync (Plaid etc.) | External API keys + approval friction; CSV import covers the need. |
| Tax-lot (FIFO) accounting | Average cost is clearer and matches brokerage apps; taxes are out of scope. |
| Dividend income projection | yfinance dividend data has no offline mock twin; listed as a stretch goal. |
| Exact day-by-day 2008 replay | Offline price cache doesn't reach 2008; beta approximation is honest and labeled. |
| AI write-access to your portfolio | Safety: the advisor reads and explains, it never edits your records. |
