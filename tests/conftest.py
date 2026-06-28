"""Shared fixtures. Forces fully-offline, deterministic mode for all tests."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

# Guarantee offline + mock before any project import reads config.
os.environ.setdefault("USE_MOCK_DATA", "1")
os.environ.setdefault("USE_MOCK_LLM", "1")


@pytest.fixture
def portfolio_db(tmp_path, monkeypatch):
    """Point the portfolio store at a fresh temp SQLite file for one test."""
    from portfolio_risk.portfolio import db as pdb

    monkeypatch.setenv("PORTFOLIO_DB_URL", f"sqlite:///{(tmp_path / 'p.db').as_posix()}")
    pdb.reset_engine()
    yield
    pdb.reset_engine()


@pytest.fixture
def dates():
    return pd.bdate_range("2022-01-03", periods=300)


@pytest.fixture
def returns_series(dates):
    rng = np.random.default_rng(7)
    return pd.Series(rng.normal(0.0005, 0.012, size=len(dates)), index=dates)


@pytest.fixture
def benchmark_series(dates):
    rng = np.random.default_rng(99)
    return pd.Series(rng.normal(0.0003, 0.010, size=len(dates)), index=dates)


@pytest.fixture
def returns_df(dates):
    rng = np.random.default_rng(123)
    data = {
        "AAA": rng.normal(0.0006, 0.013, size=len(dates)),
        "BBB": rng.normal(0.0004, 0.011, size=len(dates)),
        "CCC": rng.normal(0.0005, 0.015, size=len(dates)),
    }
    return pd.DataFrame(data, index=dates)
