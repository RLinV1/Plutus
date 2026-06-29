export interface UniverseItem {
  symbol: string;
  name: string;
}

export type Plan = "free" | "pro" | "pro_max";

export interface BillingStatus {
  plan: Plan;
  used: number;
  limit: number;
  remaining: number;
  unlimited: boolean;
  billing_enabled: boolean;
  limits: Record<Plan, number>;
}

export interface Snapshot {
  ticker: string;
  name: string;
  sector: string;
  industry?: string | null;
  description: string;
  website?: string | null;
  country?: string | null;
  employees?: number | null;
  current_price: number;
  change_pct: number;
  market_cap: number | null;
  market_cap_human: string;
  pe_ratio: number | null;
  forward_pe?: number | null;
  dividend_yield?: number | null;
  profit_margin?: number | null;
  revenue_growth?: number | null;
  recommendation?: string | null;
  analyst_target?: number | null;
  analyst_count?: number | null;
  movement: string;
  error?: string;
}

export interface Performance {
  ticker: string;
  period: string;
  total_return: number;
  return_pct: number;
  movement: string;
  movement_detail: string;
  volatility_annual_pct: number;
  error?: string;
}

export interface Technicals {
  ticker: string;
  price: number;
  sma_50: number | null;
  sma_200: number | null;
  trend: string;
  rsi: number | null;
  rsi_reading: string;
  low_52w: number | null;
  high_52w: number | null;
  range_position: number | null;
  range_reading: string;
  error?: string;
}

export interface Risk {
  ticker: string;
  compared_to: string;
  beta: number;
  sensitivity: string;
  movement: string;
  volatility_annual_pct: number;
  plain_summary: string;
  error?: string;
}

export interface PricePoint {
  t: string;
  v: number;
}

export interface PriceSeries {
  ticker: string;
  period: string;
  points: PricePoint[];
  error?: string;
}

export interface CompareRow {
  ticker: string;
  name: string;
  sector: string;
  current_price: number;
  change_pct: number;
  market_cap_human: string;
  pe_ratio: number | null;
  movement: string;
}

export interface CompareResult {
  tickers: string[];
  rows: CompareRow[];
  error?: string;
}

export interface NewsArticle {
  title: string;
  publisher: string;
  url: string;
  published: string;
  summary: string;
  relevant?: boolean;
}

export interface NewsResult {
  ticker: string;
  articles: NewsArticle[];
  error?: string;
}

export interface AskResult {
  answer: string;
  tools_used: string[];
  error?: string;
}

export interface DigestHeadline {
  title: string;
  publisher: string;
  url: string;
}

export interface DigestItem {
  ticker: string;
  period?: string;
  move_pct?: number;
  direction?: "up" | "down";
  movement_label?: string;
  current_price?: number;
  headlines?: DigestHeadline[];
  error?: string;
}

export interface DigestResult {
  period: string;
  items: DigestItem[];
  error?: string;
}

export type Period = "1d" | "1w" | "1mo" | "6mo" | "1y" | "5y" | "max";
/** Candle width for the intraday periods (1d / 1w). */
export type BarInterval = "1m" | "10m" | "1h";

/* ---------------- Portfolio workbench ---------------- */

export interface OhlcPoint {
  /** "YYYY-MM-DD" for daily candles; epoch seconds for intraday candles. */
  t: string | number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface OhlcSeries {
  ticker: string;
  period: string;
  interval?: string;
  points: OhlcPoint[];
  error?: string;
}

export interface Holding {
  ticker: string;
  name?: string;
  sector?: string;
  shares: number;
  avg_cost: number | null;
  cost_basis: number;
  price: number;
  day_change_pct: number | null;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number | null;
  realized_pnl: number;
  weight: number | null;
}

export interface PortfolioTotals {
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number | null;
  realized_pnl: number;
  day_change_pct: number | null;
}

export interface PortfolioOverview {
  portfolio: string;
  holdings: Holding[];
  totals: PortfolioTotals;
  allocation_by_sector?: Record<string, number>;
  top_position?: { ticker: string; weight: number | null };
  hhi?: number;
  concentration?: string;
  concentration_detail?: string;
  warnings?: string[];
  note?: string;
  error?: string;
}

export interface PortfolioRisk {
  portfolio: string;
  benchmark: string;
  market_value: number;
  volatility_annual_pct: number;
  beta: number;
  sharpe: number;
  max_drawdown: number;
  var_hist_95: number;
  var_mc_95: number;
  cvar_95: number;
  var_hist_95_dollars: number;
  cvar_95_dollars: number;
  hhi: number;
  concentration: string;
  correlation: { tickers: string[]; matrix: (number | null)[][] };
  highest_correlated_pair?: { tickers: string[]; correlation: number } | null;
  plain_summary: string;
  error?: string;
}

export interface Transaction {
  id: number;
  ticker: string;
  side: "BUY" | "SELL";
  shares: number;
  price: number;
  fees: number;
  trade_date: string;
  note: string;
}

export interface EquityCurve {
  portfolio: string;
  points: PricePoint[];
  twr_points: PricePoint[];
  summary?: {
    start: string;
    end: string;
    market_value_end: number;
    twr_return_pct: number | null;
    max_drawdown_pct: number | null;
  };
  note?: string;
  error?: string;
}

export interface CsvParseResult {
  rows: Omit<Transaction, "id">[];
  errors: string[];
  columns: Record<string, string>;
  committed?: boolean;
  imported?: number;
  error?: string;
}

export interface AlertRule {
  id: number;
  ticker: string;
  rule_type: string;
  threshold: number;
  enabled: boolean;
  cooldown_minutes: number;
  last_triggered_at: string | null;
}

export interface Notification {
  id: number;
  ticker: string;
  kind: string;
  title: string;
  body: string;
  read: boolean;
  created_at: string;
}

export interface ScenarioInfo {
  id: string;
  label: string;
  window: string;
  market_drop_pct: number;
}

export interface ScenarioResult {
  scenario: string;
  label: string;
  window: string;
  market_drop_pct: number;
  method: string;
  positions: {
    ticker: string;
    market_value: number;
    beta: number;
    estimated_move_pct: number;
    estimated_change: number;
  }[];
  total_value: number;
  estimated_loss: number;
  estimated_loss_pct: number;
  estimated_value_after: number;
  vs_daily_var: number | null;
  note: string;
  error?: string;
}

export interface WhatIfMetrics {
  volatility_annual_pct: number;
  beta: number;
  sharpe: number;
  var_hist_95_pct: number;
  max_drawdown_pct: number;
  hhi: number;
  top_weight_pct: number;
}

export interface WhatIfResult {
  trade: { side: string; ticker: string; shares: number; est_price: number; est_value: number };
  before: WhatIfMetrics | null;
  after: WhatIfMetrics;
  deltas: Record<string, number> | null;
  note: string;
  error?: string;
}

export interface RebalanceResult {
  target: string;
  total_value: number;
  current_weights: Record<string, number>;
  target_weights: Record<string, number>;
  drift_pct: Record<string, number>;
  suggested_trades: { ticker: string; action: string; shares: number; est_value: number }[];
  note: string;
  error?: string;
}

export interface Briefing {
  portfolio: string;
  period: string;
  totals?: PortfolioTotals;
  movers: {
    ticker: string;
    weight?: number;
    move_pct?: number;
    direction?: string;
    movement_label?: string;
    current_price?: number;
    headlines?: DigestHeadline[];
    error?: string;
  }[];
  biggest_mover?: { ticker: string; move_pct: number } | null;
  concentration?: string;
  warnings?: string[];
  unread_notifications?: Notification[];
  note?: string;
  error?: string;
}

export type QuoteMap = Record<string, { price: number | null; change_pct: number | null }>;

export interface PaperAccount {
  portfolio: string;
  start_cash: number;
  cash: number;
  positions_value: number;
  total_value: number;
  return_pct: number;
  realized_pnl: number;
  n_trades: number;
  positions: Holding[];
  transactions: Transaction[];
  note: string;
  error?: string;
}

export interface TickerIntel {
  ticker: string;
  next_earnings: string | null;
  ex_dividend_date?: string | null;
  upgrades: {
    date: string | null;
    firm: string;
    action: string;
    from_grade: string;
    to_grade: string;
  }[];
  insiders: {
    date: string | null;
    insider: string;
    position: string;
    transaction: string;
    shares: number | null;
    value: number | null;
  }[];
  institutional: {
    holder: string;
    pct_held: number | null;
    shares: number | null;
    reported: string | null;
  }[];
  error?: string;
}

export interface PaperTradeResult {
  fill?: Transaction;
  account?: PaperAccount;
  error?: string;
}

/* ---------------- Market view + fundamentals ---------------- */

export interface MarketIndex {
  symbol: string;
  name: string;
  level: number;
  change_pct: number;
}

export interface MarketOverview {
  indices: MarketIndex[];
  vix: { level: number; change_pct: number } | null;
  ten_year_yield_pct: number | null;
  mood: string;
  plain_summary: string;
  note?: string;
  error?: string;
}

export interface MoverRow {
  ticker: string;
  name: string;
  price: number;
  change_pct: number | null;
  volume: number | null;
}

export type MoverCategory = "gainers" | "losers" | "active";

export interface MoversResult {
  category: MoverCategory;
  rows: MoverRow[];
  note?: string;
  error?: string;
}

export interface Fundamentals {
  ticker: string;
  period: string | null;
  revenue: number | null;
  revenue_growth: number | null;
  net_income: number | null;
  gross_margin: number | null;
  profit_margin: number | null;
  free_cash_flow: number | null;
  total_debt: number | null;
  cash: number | null;
  equity: number | null;
  debt_to_equity: number | null;
  revenue_human: string | null;
  net_income_human: string | null;
  free_cash_flow_human: string | null;
  growth_reading: string;
  margin_reading: string;
  debt_reading: string;
  plain_summary: string;
  error?: string;
}

export interface DividendInfo {
  ticker: string;
  pays_dividend: boolean;
  dividend_yield: number | null;
  dividend_yield_pct: number;
  ttm_dividend: number;
  recent: { date: string; amount: number }[];
  ex_dividend_date: string | null;
  reading: string;
  plain_summary: string;
  error?: string;
}
