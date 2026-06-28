import { create } from "zustand";

export const VIEWS = ["research", "market", "portfolio", "paper", "scenario", "alerts", "ask"] as const;
export type View = (typeof VIEWS)[number];

export const VIEW_LABEL: Record<View, string> = {
  research: "RESEARCH",
  market: "MARKET",
  portfolio: "PORTFOLIO",
  paper: "PAPER TRADE",
  scenario: "SCENARIO LAB",
  alerts: "ALERTS",
  ask: "PLUTUS AI",
};

interface WorkspaceState {
  view: View;
  ticker: string;
  paletteOpen: boolean;
  helpOpen: boolean;
  tourOpen: boolean;
  setView: (v: View) => void;
  setTicker: (t: string) => void;
  setPaletteOpen: (open: boolean) => void;
  setHelpOpen: (open: boolean) => void;
  setTourOpen: (open: boolean) => void;
  /** Jump to a ticker and make sure the research view is showing it. */
  openTicker: (t: string) => void;
}

export const useWorkspace = create<WorkspaceState>((set) => ({
  view: "research",
  ticker: "AAPL",
  paletteOpen: false,
  helpOpen: false,
  tourOpen: false,
  setView: (view) => set({ view }),
  setTicker: (ticker) => set({ ticker: ticker.toUpperCase() }),
  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
  setHelpOpen: (helpOpen) => set({ helpOpen }),
  setTourOpen: (tourOpen) => set({ tourOpen }),
  openTicker: (t) => set({ ticker: t.toUpperCase(), view: "research" }),
}));
