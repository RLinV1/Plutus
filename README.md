# Stock Research Assistant â€” AI-native, beginner-friendly

A friendly **AI stock research assistant** built around the **Model Context
Protocol (MCP)**. Ask about a stock in plain English and get real data plus
plain-language explanations. It combines the three skills that matter most for
modern AI engineering into one project:

1. **RAG** â€” retrieval over plain-English company profiles, "what to watch out
   for" notes, and investing-basics explainers.
2. **Autonomous agent** â€” a Claude agent that calls the MCP server's tools to
   answer natural-language questions and cite sources.
3. **Eval harness** â€” a test-and-self-correct loop that scores the agent's tool
   selection and numeric accuracy against ground truth.

It uses **live market data by default** (yfinance) and runs the agent **with zero
API keys** (a rule-based mock agent). Add an `ANTHROPIC_API_KEY` for real Claude,
or set `USE_MOCK_DATA=1` for fully-offline, deterministic data.

> **Educational only â€” not investment advice.** It cannot predict prices.

---

## What it does

You ask, in plain English:

> *"How has Apple done this year, and is it above its 200-day average?"*

The agent picks the right MCP tools, computes the numbers from live prices,
retrieves any relevant background from the knowledge library, and answers in
plain language â€” translating jargon (market cap, P/E, the 200-day moving average,
volatility) as it goes.

### The ten tools

| Tool | Answers questions like |
|---|---|
| `get_stock_snapshot` | "Tell me about Apple" â€” name, sector, price, daily move, market cap, P/E |
| `get_price_performance` | "How has Nvidia done this year?" â€” % return + "calm/average/bumpy" |
| `compare_stocks` | "Compare Apple and Microsoft" â€” side-by-side basics |
| `explain_stock_risk` | "Is Tesla risky?" â€” beta + volatility in plain words |
| `get_technical_indicators` | "Is Apple above its 200-day average?" â€” SMAs, RSI, 52-week range |
| `get_ticker_news` | "What's the latest on Apple?" â€” recent headlines (free, keyless) |
| `explain_price_move` | "Why did Apple drop?" â€” the move + same-window news that may explain it |
| `get_filing_risks` | "What are the risks in Apple's 10-K?" â€” SEC risk factors in plain English |
| `get_watchlist_digest` | "What moved on my watchlist?" â€” per-ticker move + headlines (daily digest) |
| `search_knowledge` | "What's a P/E ratio?" / "Why invest in Nvidia?" â€” cited RAG lookups |

Numbers (volatility, beta, moving averages, RSI) are computed by pure
`numpy`/`pandas`/`scipy` code in `risk/metrics.py` and `risk/indicators.py`, then
translated into plain English.

---

## Architecture

```
 Claude / mock agent            MCP server (stdio, FastMCP)        engine
 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€            â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€        â”€â”€â”€â”€â”€â”€
 agent/client.py        â”€â”€â–º     server/mcp_server.py        â”€â”€â–º   tools.py
   â€¢ real: tool_runner            @mcp.tool wrappers                â”œâ”€ risk/metrics.py
   â€¢ mock: mock_agent.py          (thin; delegate to tools.py)      â”œâ”€ risk/indicators.py
                                                                    â”œâ”€ data/market_data.py (live yfinance | mock)
                                                                    â”‚   â”œâ”€ get_prices()  + parquet cache
                                                                    â”‚   â””â”€ get_company_info() + JSON cache
                                                                    â””â”€ rag/ (Chroma + MiniLM)
 evals/run_evals.py  â”€â”€ scores agent vs. ground truth from the same engine (mock data)
```

**Key design choice:** tool logic lives once in `src/portfolio_risk/tools.py`.
The MCP server, the mock agent, and the tests all call it â€” so the eval's
"ground truth" is computed by the exact same engine the agent invokes.

**How RAG + MCP connect (the 200-day SMA example):** "Is Apple above its 200-day
average?" needs a live number â†’ the agent calls the `get_technical_indicators`
**MCP tool**. "What *is* a 200-day average?" needs a stable explanation â†’ the
agent calls `search_knowledge` (**RAG**). Use a tool for changing numbers/facts;
use RAG for stable concepts/background.

### Project layout
```
src/portfolio_risk/
  config.py            paths, constants, mode switches (live vs mock)
  tools.py             the 10 tools (single source of truth)
  data/
    market_data.py     live yfinance prices + company .info (cached); mock twin
    mock_data.py       deterministic GBM prices + synthetic company info
    loader.py          tickers -> aligned (returns_df, benchmark)
    returns.py         price -> returns, alignment
  risk/
    metrics.py         pure math (volatility, beta, drawdown, VaR family, ...)
    indicators.py      SMA, RSI, 52-week range
    portfolio.py       Portfolio + compute_portfolio_report() (kept for tests)
  rag/
    store.py           Chroma client + local MiniLM embeddings
    ingest.py          chunk+embed seed docs; optional SEC EDGAR pull
    search.py          search_knowledge()
    seed/              plain-English corpus (investing basics, indicators, profiles)
  server/mcp_server.py FastMCP server (stdio)
  agent/
    client.py          dispatch: mock agent or real Claude
    mock_agent.py      deterministic rule-based agent (no API key)
    prompts.py         system prompt
api/server.py          FastAPI backend exposing the 10 tools over HTTP
frontend/              React + Vite + TypeScript single-page UI (calls /api)
tests/                 offline tool + math + RAG tests
evals/                 questions.jsonl + run_evals.py (self-correction) + report.py
```

---

## Local setup

The app has two parts: a **Python backend** (FastAPI + the tools/agent/RAG) and a
**React + Vite frontend**. You set both up once, then run them together.

### Prerequisites
| Need | Why |
|---|---|
| **Python 3.13** (`py -3.13` on Windows, `python3.13` elsewhere) | The default 3.14 lacks `torch`/`chromadb` wheels. |
| **Node.js 18+** (includes `npm`) | Builds/serves the React frontend. |

### One-time setup

```powershell
# 0. From the project root
cd "C:\Users\rlin7\OneDrive\Documents\Codepath\RAG-AI-MCP"

# 1. Python backend: create the venv and install (editable + dev tools)
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process RemoteSigned
python -m pip install --upgrade pip
pip install -e ".[dev]"               # first run pulls torch + chromadb (a few minutes)

# 2. Frontend: install the npm packages
cd frontend
npm install
cd ..

# 3. Build the RAG knowledge library (one-time; downloads the ~80MB MiniLM model once)
python -m portfolio_risk.rag.ingest

# 4. (optional) create a .env you can edit
copy .env.example .env
```

> macOS / Linux: use `python3.13 -m venv .venv` then `source .venv/bin/activate`,
> and `cp .env.example .env`.

### Run the web app (two terminals)

The frontend calls the backend, so run both. The Vite dev server proxies
`/api/*` to the backend, so there's nothing else to configure.

```powershell
# Terminal 1 â€” backend  ->  http://127.0.0.1:8000
.\.venv\Scripts\Activate.ps1
python -m api.server                  # or: stock-api

# Terminal 2 â€” frontend  ->  http://localhost:5173   (open this one)
cd frontend
npm run dev
```

Open **http://localhost:5173**. Stock data is **live from yfinance** by default.

### Other ways to run

```powershell
# Ask the assistant from the CLI (mock agent â€” no API key needed)
python -m portfolio_risk.agent.client "Tell me about Apple"
python -m portfolio_risk.agent.client "Is Apple above its 200-day average?"

# Tests â€” fully offline & deterministic
$env:USE_MOCK_DATA = "1"; pytest

# Eval harness (forces deterministic mock data internally)
python -m evals.run_evals
```

> For real Claude in the **Ask** tab, set `ANTHROPIC_API_KEY` before starting the
> backend. For fully-offline data, set `USE_MOCK_DATA=1`. More detail in
> [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

---

## Modes: live vs. mock, mock vs. real Claude

| Variable | Default | Effect |
|---|---|---|
| `USE_MOCK_DATA` | `0` | `0` = live yfinance (prices + company info), cached to `data/cache/`. `1` = deterministic synthetic data (offline). |
| `USE_MOCK_LLM` | `auto` | `auto` = mock agent unless `ANTHROPIC_API_KEY` is set. Force with `1`/`0`. |
| `ANTHROPIC_API_KEY` | *(empty)* | Add to enable the real Claude agent (model `claude-opus-4-8`). |
| `EDGAR_USER_AGENT` | â€” | Only for `rag.ingest --edgar` (SEC requires a descriptive UA). |

```powershell
$env:USE_MOCK_DATA = "1"            # offline synthetic data
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # real Claude agent
python -m portfolio_risk.agent.client "Compare Apple, Microsoft, and Nvidia."
```

> **Can I run Claude locally / via Ollama?** No â€” Claude is a closed-weight model,
> available only through the Anthropic API (or Bedrock/Vertex). Ollama runs
> open-weight models (Llama, Mistral, Qwen, â€¦). The mock agent is the offline
> option here; a local open LLM would be a separate backend.

---

## Using it from Claude Desktop (optional)

Add to `%APPDATA%\Claude\claude_desktop_config.json` and restart Claude Desktop:

```json
{
  "mcpServers": {
    "stock-research-assistant": {
      "command": "C:\\Users\\rlin7\\OneDrive\\Documents\\Codepath\\RAG-AI-MCP\\.venv\\Scripts\\python.exe",
      "args": ["-m", "portfolio_risk.server.mcp_server"],
      "env": { "PYTHONPATH": "C:\\Users\\rlin7\\OneDrive\\Documents\\Codepath\\RAG-AI-MCP\\src" }
    }
  }
}
```

The ten tools then appear in Claude Desktop chat. Inspect the server during
development with `mcp dev src/portfolio_risk/server/mcp_server.py`.

---

## The eval harness

`python -m evals.run_evals` runs each question in `evals/questions.jsonl`, checks
(1) the agent called the expected tool and (2) the extracted number is within
tolerance of ground truth (computed by the same engine on the same deterministic
data), and on failure **re-prompts once with a corrective hint** and re-scores.
It forces `USE_MOCK_DATA=1` so grading is reproducible, and reports first-pass and
post-retry pass rates.

---

## Notes, conventions, gotchas

- **stdio servers must never print to stdout** â€” it corrupts JSON-RPC. All logs
  go to stderr; Chroma/sentence-transformers/yfinance banners are silenced.
- **Chroma downloads MiniLM (~80MB) once** on first ingest, not in a tool call.
- **yfinance is flaky** â€” live prices/info are cached; tests and evals set
  `USE_MOCK_DATA=1` so they never depend on the network.
- Mock prices and company info are **pure-from-hash** so they're identical every
  run â€” that's what keeps the evals reproducible.
- **Claude params:** model `claude-opus-4-8`, `thinking={"type":"adaptive"}` only.
- The corpus docs are **illustrative, beginner-friendly summaries**, not real SEC
  filings. (`python -m portfolio_risk.rag.ingest --edgar AAPL` can still pull real
  10-K text from SEC EDGAR if you want it.)
- **Not investment advice.**

See **CLAUDE.md** for the design rationale and context for future work.
