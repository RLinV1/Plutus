# Developer Setup & Local Hosting

How to set up the dev environment and run every surface of the Stock Research
Assistant locally — the **React web app** (Vite frontend + FastAPI backend), the
**agent CLI**, the **MCP server**, the **tests**, and the **eval harness**. Stock
data comes from **live yfinance** by default; tests/evals force offline mock data.

---

## 0. Prerequisites

| Path | Need |
|---|---|
| Local venv | **Python 3.13** (`py -3.13` on Windows; `python3.13` on macOS/Linux). Avoid 3.14 — `torch`/`chromadb` lack wheels for it. |
| Frontend | **Node.js 18+** (ships with npm) for the React + Vite UI. |
| Docker | **Docker Desktop** (Compose v2) for the backend/CLI image. |

> Why 3.13: `requires-python` is pinned to `>=3.10,<3.14`. On 3.14, pip tries to
> build torch/chromadb from source and fails on Windows.

---

## 1. Local venv setup

### Windows (PowerShell)
```powershell
cd "C:\Users\rlin7\OneDrive\Documents\Codepath\RAG-AI-MCP"

py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
# If activation is blocked by execution policy:
#   Set-ExecutionPolicy -Scope Process RemoteSigned

python -m pip install --upgrade pip
pip install -e ".[dev]"

copy .env.example .env        # optional; all blanks are fine for mock mode
```

### macOS / Linux (bash)
```bash
cd /path/to/RAG-AI-MCP
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
```

`pip install -e ".[dev]"` installs the package **editable** (code changes take
effect immediately) plus dev tools (`pytest`, `empyrical-reloaded`). First
install pulls torch + chromadb and takes a few minutes.

---

## 2. One-time RAG ingest

Builds the vector store from the bundled corpus. Downloads the MiniLM embedding
model (~80MB) **once**.

```bash
python -m portfolio_risk.rag.ingest
# Optional: also pull real 10-K risk factors from SEC EDGAR
#   (set EDGAR_USER_AGENT in .env first)
python -m portfolio_risk.rag.ingest --edgar AAPL MSFT
```

Artifacts land in `data/chroma/` (gitignored).

---

## 3. Run everything (local venv)

```bash
# Tests — fully offline, deterministic
USE_MOCK_DATA=1 pytest

# Web app = two processes:
python -m api.server                 # backend API -> http://127.0.0.1:8000 (or: stock-api)
cd frontend && npm install && npm run dev   # UI -> http://localhost:5173 (proxies /api)

# Agent CLI (mock agent unless ANTHROPIC_API_KEY is set)
python -m portfolio_risk.agent.client "Tell me about Apple, and is it above its 200-day average?"

# Eval harness (tool-choice + numeric scoring, self-correction loop)
python -m evals.run_evals

# MCP server (stdio JSON-RPC — used by Claude Desktop / the agent)
python -m portfolio_risk.server.mcp_server
# Inspect interactively:
mcp dev src/portfolio_risk/server/mcp_server.py
```

> The MCP server speaks JSON-RPC on stdout — don't pipe junk into it; run it via
> a client (the agent, Claude Desktop, or `mcp dev`), not by hand.

---

## 4. Hosting the web app locally

The web app is two processes: a **FastAPI backend** (thin HTTP layer over
`tools.py`) and a **React + Vite frontend** that calls it. The Vite dev server
proxies `/api/*` to the backend, so there are no CORS issues.

```bash
# Terminal 1 — backend (live yfinance data by default)
python -m api.server            # or: stock-api   -> http://127.0.0.1:8000

# Terminal 2 — frontend
cd frontend
npm install                     # first time only
npm run dev                     # -> http://localhost:5173
```

Open **http://localhost:5173**. Tabs: **Overview** (price, market cap, P/E, 50/200-day
averages, RSI, 52-week range, plain-English risk), **Performance** (segmented
1M/6M/1Y/5Y control + chart), **Compare**, and **Ask** (the agent).

```bash
# Health check:
curl http://127.0.0.1:8000/api/health     # -> {"ok":true,"live_data":true}
```

> Backend in Docker: `docker compose up api` serves the API on :8000. The React
> dev server runs on the host via `npm run dev` (it isn't containerized).

---

## 5. Docker / dev container details

### Plain Compose
```bash
docker compose build                                # build the image once
docker compose run --rm app pytest                  # tests
docker compose run --rm app python -m portfolio_risk.rag.ingest
docker compose run --rm app python -m evals.run_evals
docker compose up api                               # the FastAPI backend on :8000
docker compose up -d app && docker compose exec app bash   # shell in
docker compose down
```
- `app` service: general CLI + dev container (`sleep infinity`).
- `api` service: FastAPI/uvicorn on :8000 (pair with `npm run dev` on the host).
- Image: Python 3.13 + **CPU-only** torch (small). Source is bind-mounted; the
  MiniLM model persists in the `hf-cache` named volume.

### VS Code dev container
1. Install the **Dev Containers** extension.
2. **"Reopen in Container"** → builds the image, installs the editable package,
   ingests the corpus, wires up pytest.
3. Config: `.devcontainer/devcontainer.json`.

---

## 6. Modes: mock ↔ live

All offline by default. Switches (see `.env.example`):

| Variable | Default | Effect |
|---|---|---|
| `USE_MOCK_DATA` | `0` | `0` = live yfinance (cached to `data/cache/`). `1` = synthetic prices (offline; used by tests/evals). |
| `USE_MOCK_LLM` | `auto` | `auto` = mock agent unless `ANTHROPIC_API_KEY` set. Force `1`/`0`. |
| `ANTHROPIC_API_KEY` | empty | Enables the real Claude agent (`claude-opus-4-8`). |
| `EDGAR_USER_AGENT` | — | Required only for `rag.ingest --edgar` (SEC needs a descriptive UA). |

Set them in `.env`, your shell, or inline:
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-..."; python -m api.server   # real Claude in the Ask tab
```

---

## 7. Connect to Claude Desktop (optional)

Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) and restart:
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
The ten tools then appear in Claude Desktop chat.

---

## 8. Project layout (where things live)

```
src/portfolio_risk/
  tools.py            the 10 tools (single source of truth)
  risk/               pure math: metrics + technical indicators
  data/               mock/live prices, caching, return transforms
  rag/                Chroma store, ingest, search, seed corpus
  server/mcp_server.py FastMCP stdio server
  agent/              mock agent + real Claude client
api/server.py         FastAPI backend (HTTP layer over tools.py)
frontend/             React + Vite + TypeScript single-page UI
tests/                offline pytest suite
evals/                questions.jsonl + run_evals.py + report.py
docs/                 this file
Dockerfile, docker-compose.yml, .devcontainer/   reproducible env
```

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `pip` builds torch from source / fails | You're on Python 3.14. Recreate the venv with `py -3.13`. |
| Activation blocked (PowerShell) | `Set-ExecutionPolicy -Scope Process RemoteSigned` |
| HuggingFace "symlinks not supported" warning (Windows) | Harmless. Silence with `HF_HUB_DISABLE_SYMLINKS_WARNING=1`, or enable Developer Mode. |
| Frontend shows no data / network errors | Make sure the backend is running (`python -m api.server`) — the Vite dev server proxies `/api` to `127.0.0.1:8000`. |
| Port 5173 or 8000 already in use | Change the Vite port in `frontend/vite.config.ts`, or the uvicorn port in `api/server.py`. |
| `search_knowledge` returns nothing | Run `python -m portfolio_risk.rag.ingest` first. |
| MCP server "disconnects" immediately | Something printed to stdout. Keep all logs on stderr (the code already does). |
| yfinance errors / empty data | Set `USE_MOCK_DATA=1` for offline data, or retry — live data is flaky and cached. |

---

## 10. Daily workflow

```bash
# activate venv (or open the dev container), then:
USE_MOCK_DATA=1 pytest      # keep this green
python -m api.server        # backend; in another terminal: cd frontend && npm run dev
python -m evals.run_evals
```

Editable install means source edits are live — no reinstall needed unless you
change `pyproject.toml` dependencies (then `pip install -e ".[dev]"` again).
Not investment advice.
