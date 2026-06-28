# PortfolioRisk MCP — reproducible dev/runtime image.
# Python 3.13 (matches the project's requires-python ">=3.10,<3.14").
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Default to the fully-offline mock mode; override at run time.
    USE_MOCK_DATA=1 \
    USE_MOCK_LLM=auto \
    # Persist the HuggingFace MiniLM embedding model in a stable location.
    HF_HOME=/opt/hf-cache

WORKDIR /workspace

# build-essential: peewee (an empyrical-reloaded dep) builds from sdist.
# git/curl: convenience for dev containers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git curl \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first (much smaller than the default CUDA wheel), then
# the project deps. Copy only the metadata + package tree needed for the
# editable install so this layer caches across source edits.
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -e ".[dev]"

# Copy the rest (tests, evals, seed corpus already under src).
COPY . .

# Default: answer a sample question with the offline mock agent. In a dev
# container this is overridden by docker-compose (`sleep infinity`).
CMD ["python", "-m", "portfolio_risk.agent.client", \
     "What is the 95% VaR of 60% AAPL and 40% MSFT?"]
