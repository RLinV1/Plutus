# Infrastructure & Architecture — and *why*

This document explains how the Stock Research Assistant is deployed and **why each
technology was chosen**. The app is a React frontend over a FastAPI backend that
wraps a shared tool layer (`tools.py`), an MCP server, a RAG knowledge base, and a
Claude agent. The pieces below make it **scalable, cheaper to run, and durable**
while staying easy to run locally and offline for tests.

> Design rule that shapes everything: every new layer **degrades gracefully**.
> Unset `REDIS_URL` → in-process cache. Unset `DATABASE_URL` → DB no-ops. Unset
> `RAG_BACKEND` → embedded Chroma. So `pytest`/evals stay deterministic with zero
> infrastructure, and a Redis/Postgres outage never fails a request.

---

## 1. Topology

```
                         ┌────────────────────────────────────────┐
  browser  ──────────►   │  frontend  (nginx :8080)               │
                         │   ├─ /         → static Vite SPA        │
                         │   └─ /api/*    → reverse-proxy           │
                         └───────────────┬────────────────────────┘
                                         ▼
                         ┌────────────────────────────────────────┐
                         │  api  (FastAPI/uvicorn :8000)  [×N]      │
                         │   tools.py · agent · /api/ask_stream SSE │
                         └───┬───────────────┬──────────────┬──────┘
                  cache reads│         shared state         │ spawns per request
                             ▼               ▼              ▼
                       ┌─────────┐   ┌──────────────────┐  ┌──────────────┐
                       │  Redis  │   │ Postgres+pgvector│  │  MCP server  │
                       │ (cache) │   │ news·docs·vectors│  │ (subprocess) │
                       └─────────┘   └──────────────────┘  └──────────────┘
                                              ▲
                         ┌────────────────────┘
                         │  ingest worker (one-shot): seed + EDGAR + news → RAG
                         └──────────────────────────────────────────────────────
  app  (dev container / offline tests — no DB/Redis env)
```

One command — `docker compose up --build` — brings up frontend, api, redis,
postgres; `docker compose run --rm ingest` builds the RAG corpus.

---

## 2. Why Docker Compose

Each concern runs in its own container with a pinned image, wired together by one
declarative file. Benefits over "run five processes by hand":

- **Reproducible** — same images and config on any machine; no "works on my laptop."
- **Scalable** — `docker compose up --scale api=3` runs multiple backend replicas;
  because all state lives in Redis/Postgres, replicas are interchangeable.
- **Isolated & swappable** — Redis/Postgres/nginx are standard images; we don't
  hand-manage them.
- **Dev/prod parity** — the base file is dev-friendly (bind mounts, exposed ports,
  a `app` dev-container service); `docker-compose.prod.yml` overlays production
  settings (no bind mounts, only the frontend published, `restart: unless-stopped`).

---

## 3. Why a single nginx entry point

In production the React app is a **static build** served by nginx, which also
reverse-proxies `/api/*` to the backend. So there's **one origin**:

- **No CORS** in prod (same origin); the Vite dev-server proxy is dev-only.
- A natural place to terminate TLS, gzip static assets, and load-balance API replicas.
- **SSE works** because the `/api/ask_stream` location disables proxy buffering
  (`proxy_buffering off` + `X-Accel-Buffering: no` + a long read timeout) — otherwise
  nginx would buffer the whole streamed answer and it would appear only when finished.

---

## 4. Why Redis (vs Memcached / in-process)

The app caches expensive calls: yfinance quotes/news/company-info and **Claude
answers**. Originally these were in-process Python dicts — fine for one process,
useless across replicas (each has its own, none survive a restart).

**Redis** is a shared, TTL'd cache so every stateless API replica gets the same
cache hits — the key enabler for horizontal scaling — and it cuts both yfinance load
and (notably) paid Claude API spend. Keys are namespaced/versioned with TTLs:
`q:v1:{T}` 20s, `news:v1:{T}` 5m, `info:v1:{T}` 2d, `ans:v1:{hash(question)}` 15m.

- *Memcached* would also work but lacks Redis's richer types/persistence and is less
  common in this ecosystem — no upside here.
- *In-process* can't be shared and dies on restart.

`cache.py` wraps Redis behind a tiny `get/set-json` API and **falls back to an
in-process dict** when `REDIS_URL` is unset or Redis is unreachable — so offline dev
and tests are unaffected.

---

## 5. Why Postgres + pgvector (vs OpenSearch / Chroma)

One durable service stores **documents, news, and vector embeddings** together and
supports **hybrid search**:

- **pgvector** gives semantic vector (cosine) search; Postgres **tsvector** gives
  keyword full-text search. We fuse them (see §7) for results neither alone gets.
- **Replica-safe** — a real client/server DB (unlike a bind-mounted embedded
  Chroma SQLite file, which corrupts under concurrent writers from multiple replicas).
- **Light** — a few hundred MB of RAM; great for a laptop demo.

*OpenSearch/Elasticsearch* is the more powerful "enterprise search" option (BM25 +
kNN + rerank) but needs ~1.5–2 GB of JVM RAM and is a separate store from the
relational data — overkill here. *Embedded Chroma* stays the zero-setup default
(`RAG_BACKEND=chroma`) and the automatic fallback, but it's dense-vector only and
not safe to share across writers.

---

## 6. Why persist news/documents in a database

Previously news was fetched live from yfinance and only cached in memory — it
vanished on restart. Storing it in Postgres (`news` table, deduped by
`(ticker, url)`) gives:

- **History** that survives restarts and **fewer yfinance calls** (read-through:
  cache → DB → yfinance; on a yfinance outage we fall back to recent DB rows).
- A **corpus to enrich RAG** — the ingest worker folds persisted news into the
  searchable index, plus real **SEC EDGAR 10-K** filings, alongside the seed docs.
- A `documents` table tracks what's been ingested.

The **ingest worker** (`python -m portfolio_risk.rag.ingest --all`) is a one-shot
container that builds the schema and loads seed + EDGAR + news into the vector store.

---

## 7. Why advanced RAG (hybrid + RRF + reranker)

Pure vector search misses exact terms (tickers, product names, numbers); pure
keyword search misses paraphrases. So retrieval (`rag/pg_store.py`) runs **both**:

1. **Dense** — pgvector cosine nearest-neighbours (semantic).
2. **Lexical** — Postgres `tsvector` full-text (keyword).
3. **Reciprocal Rank Fusion** combines the two rankings (`Σ 1/(60+rank)`) — robust,
   no score-normalization needed.
4. **Optional cross-encoder reranker** (`RAG_RERANK=1`) re-scores the top candidates
   for precision — the highest-impact quality lever (downloads a small model once).

The corpus is also expanded beyond the seed docs to **news + EDGAR filings**, so the
agent can ground "what's happening with X" / "what are the risks" in real documents
with citations.

---

## 8. Why the MCP server stays an in-container subprocess

The agent talks to tools over **MCP (stdio)**, spawning
`python -m portfolio_risk.server.mcp_server` per request. It is **stateless and
cheap**, and the API image already contains the package, so the subprocess just
works. Splitting it into its own service would require rewriting the agent to a
streamable-HTTP MCP client for **zero scaling benefit** — the tools it calls already
share Redis/Postgres. (The non-AI tabs — snapshot/news/compare — don't use MCP at
all; they call `tools.py` directly through FastAPI.)

---

## 9. Scaling & failure model

- **Scales:** the `api` service (`--scale api=N`); nginx load-balances and shared
  state lives in Redis/Postgres.
- **Healthchecks + `depends_on`** gate startup order (api waits for redis + postgres
  healthy); the frontend waits for api.
- **Graceful degradation:** cache → in-process dict; news → Postgres → yfinance →
  `[]`; pgvector RAG → Chroma fallback; every tool returns `{"error": ...}` rather
  than crashing. No single dependency outage fails a whole request.

---

## 10. Local / offline & determinism

- `app` (the dev-container/test service) is started **without** `DATABASE_URL`/
  `REDIS_URL`/`RAG_BACKEND`, so `docker compose run --rm app pytest` is fully offline.
- Tests force `USE_MOCK_DATA=1`/`USE_MOCK_LLM=1`; all infra layers sit *after* those
  mock guards and no-op when their env vars are unset, so the eval harness stays
  deterministic and the default RAG backend remains embedded Chroma.

---

## Quick reference

| Concern | Tech | Service | Env toggle |
|---|---|---|---|
| Static UI + routing/TLS | nginx | `frontend` (:8080) | — |
| HTTP API + agent | FastAPI/uvicorn | `api` (:8000, scalable) | `USE_MOCK_*`, `ANTHROPIC_API_KEY` |
| Shared cache | Redis | `redis` | `REDIS_URL` |
| News + docs + vectors | Postgres + pgvector | `postgres` | `DATABASE_URL` |
| RAG backend / rerank | pgvector hybrid / Chroma | (in api) | `RAG_BACKEND`, `RAG_RERANK` |
| Corpus builder | ingest worker | `ingest` (one-shot) | — |
| Tools over MCP | stdio subprocess | (in api) | — |
| Dev shell / tests | image | `app` (offline) | — |

Run: `docker compose up --build` → http://localhost:8080 ; `docker compose run --rm ingest` to build the corpus.
