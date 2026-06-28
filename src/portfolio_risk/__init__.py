"""PortfolioRisk MCP — AI-native portfolio risk management.

Packages:
- data:   market data (mock or live yfinance) + return transforms
- risk:   pure risk-metric math (VaR, CVaR, Sharpe, beta, drawdown, ...)
- rag:    Chroma-backed retrieval over financial filings / risk-policy docs
- server: FastMCP server exposing the risk + RAG tools over stdio
- agent:  Claude (or mock) client that consumes the MCP server
"""

__version__ = "0.1.0"
