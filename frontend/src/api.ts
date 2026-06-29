import type {
  AlertRule,
  AskResult,
  BillingStatus,
  Briefing,
  CompareResult,
  CsvParseResult,
  DigestResult,
  DividendInfo,
  EquityCurve,
  Fundamentals,
  MarketOverview,
  MoverCategory,
  MoversResult,
  NewsResult,
  Notification,
  OhlcSeries,
  PaperAccount,
  PaperTradeResult,
  Performance,
  PortfolioOverview,
  PortfolioRisk,
  PriceSeries,
  RebalanceResult,
  Risk,
  ScenarioInfo,
  ScenarioResult,
  Snapshot,
  Technicals,
  TickerIntel,
  Transaction,
  UniverseItem,
  WhatIfResult,
} from "./types";

// Injected by the React auth layer (ClerkTokenSync in App.tsx) when Clerk is enabled.
let _getToken: (() => Promise<string | null>) | null = null;

export function setTokenGetter(fn: () => Promise<string | null>) {
  _getToken = fn;
}

export async function authHeaders(): Promise<Record<string, string>> {
  const token = _getToken ? await _getToken() : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: await authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

async function sendJSON<T>(url: string, body: unknown, method = "POST"): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

const q = (s: string) => encodeURIComponent(s);

export const api = {
  universe: () =>
    getJSON<{ tickers: UniverseItem[] }>("/api/universe").then((d) => d.tickers),
  snapshot: (t: string) => getJSON<Snapshot>(`/api/snapshot?ticker=${q(t)}`),
  performance: (t: string, p: string) =>
    getJSON<Performance>(`/api/performance?ticker=${q(t)}&period=${q(p)}`),
  technicals: (t: string) => getJSON<Technicals>(`/api/technicals?ticker=${q(t)}`),
  risk: (t: string) => getJSON<Risk>(`/api/risk?ticker=${q(t)}`),
  prices: (t: string, p: string) =>
    getJSON<PriceSeries>(`/api/prices?ticker=${q(t)}&period=${q(p)}`),
  compare: (tickers: string[]) =>
    getJSON<CompareResult>(`/api/compare?tickers=${q(tickers.join(","))}`),
  news: (t: string) => getJSON<NewsResult>(`/api/news?ticker=${q(t)}`),
  market: () => getJSON<MarketOverview>("/api/market"),
  movers: (category: MoverCategory) =>
    getJSON<MoversResult>(`/api/movers?category=${q(category)}`),
  fundamentals: (t: string) =>
    getJSON<Fundamentals>(`/api/fundamentals?ticker=${q(t)}`),
  dividends: (t: string) => getJSON<DividendInfo>(`/api/dividends?ticker=${q(t)}`),
  digest: (tickers: string[], period = "1d") =>
    getJSON<DigestResult>(`/api/digest?tickers=${q(tickers.join(","))}&period=${q(period)}`),
  ask: async (question: string): Promise<AskResult> => {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    return (await res.json()) as AskResult;
  },

  /* ---- portfolio workbench ---- */
  ohlc: (t: string, p: string, interval = "1d") =>
    getJSON<OhlcSeries>(`/api/ohlc?ticker=${q(t)}&period=${q(p)}&interval=${q(interval)}`),
  intel: (t: string) => getJSON<TickerIntel>(`/api/intel?ticker=${q(t)}`),
  portfolio: (name = "default") =>
    getJSON<PortfolioOverview>(`/api/portfolio/${q(name)}`),
  portfolioRisk: (name = "default") =>
    getJSON<PortfolioRisk>(`/api/portfolio/${q(name)}/risk`),
  equityCurve: (name = "default") =>
    getJSON<EquityCurve>(`/api/portfolio/${q(name)}/equity_curve`),
  transactions: (name = "default") =>
    getJSON<{ transactions: Transaction[] }>(
      `/api/portfolio/${q(name)}/transactions`,
    ).then((d) => d.transactions),
  addTransaction: (name: string, t: Partial<Transaction>) =>
    sendJSON<Transaction & { error?: string }>(
      `/api/portfolio/${q(name)}/transactions`,
      t,
    ),
  deleteTransaction: (id: number) =>
    sendJSON<{ deleted: boolean }>(`/api/portfolio/transactions/${id}`, undefined, "DELETE"),
  resetPortfolio: (name: string, confirm: string) =>
    sendJSON<{ reset?: boolean; deleted?: number; error?: string }>(
      `/api/portfolio/${q(name)}/reset`,
      { confirm },
    ),
  importCsv: (name: string, csv: string, commit: boolean) =>
    sendJSON<CsvParseResult>(`/api/portfolio/${q(name)}/import_csv`, { csv, commit }),
  briefing: (name = "default", period = "1d") =>
    getJSON<Briefing>(`/api/portfolio/${q(name)}/briefing?period=${q(period)}`),
  scenarios: () =>
    getJSON<{ scenarios: ScenarioInfo[] }>("/api/scenarios").then((d) => d.scenarios),
  scenario: (name: string, scenario: string) =>
    getJSON<ScenarioResult>(`/api/portfolio/${q(name)}/scenario?scenario=${q(scenario)}`),
  scenarioBasket: (positions: { ticker: string; value: number }[], scenario: string) =>
    sendJSON<ScenarioResult>("/api/scenario/basket", { positions, scenario }),
  simulate: (name: string, side: string, ticker: string, shares: number) =>
    sendJSON<WhatIfResult>(`/api/portfolio/${q(name)}/simulate`, { side, ticker, shares }),
  rebalance: (name = "default", target = "equal_weight") =>
    getJSON<RebalanceResult>(`/api/portfolio/${q(name)}/rebalance?target=${q(target)}`),
  alerts: () => getJSON<{ rules: AlertRule[] }>("/api/alerts").then((d) => d.rules),
  addAlert: (r: { ticker: string; rule_type: string; threshold: number; cooldown_minutes?: number }) =>
    sendJSON<AlertRule & { error?: string }>("/api/alerts", r),
  toggleAlert: (id: number, enabled: boolean) =>
    sendJSON<AlertRule>(`/api/alerts/${id}`, { enabled }, "PATCH"),
  deleteAlert: (id: number) =>
    sendJSON<{ deleted: boolean }>(`/api/alerts/${id}`, undefined, "DELETE"),
  paperAccount: () => getJSON<PaperAccount>("/api/paper/account"),
  paperTrade: (side: string, ticker: string, shares: number) =>
    sendJSON<PaperTradeResult>("/api/paper/trade", { side, ticker, shares }),
  paperReset: () =>
    sendJSON<{ reset: boolean; deleted: number }>("/api/paper/reset", {}),
  notifications: (unread = false) =>
    getJSON<{ notifications: Notification[] }>(
      `/api/notifications?unread=${unread ? 1 : 0}&limit=50`,
    ).then((d) => d.notifications),
  markRead: (ids?: number[]) =>
    sendJSON<{ marked: number }>("/api/notifications/read", ids ? { ids } : {}),
  health: () =>
    getJSON<{ live_data: boolean; ws_clients: number }>("/api/health"),

  /* ---- billing / quota ---- */
  billingStatus: () => getJSON<BillingStatus>("/api/billing/status"),
  billingCheckout: (plan: "pro" | "pro_max") =>
    sendJSON<{ url: string }>("/api/billing/checkout", { plan }),
  billingPortal: () => sendJSON<{ url: string }>("/api/billing/portal", {}),
};
