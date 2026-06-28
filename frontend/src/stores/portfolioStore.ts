import { create } from "zustand";

/** Which portfolio the workbench is looking at. "default" is the user's own;
 *  "demo" holds the bundled sample transactions so new users can explore
 *  without entering anything. Persisted across sessions. */
const KEY = "st.portfolio";

export const PORTFOLIO_TABS = [
  { id: "default", label: "MY PORTFOLIO" },
  { id: "demo", label: "DEMO" },
] as const;

interface PortfolioState {
  name: string;
  setName: (n: string) => void;
}

export const usePortfolio = create<PortfolioState>((set) => ({
  name: localStorage.getItem(KEY) || "default",
  setName: (name) => {
    try {
      localStorage.setItem(KEY, name);
    } catch {
      /* quota/availability — non-fatal */
    }
    set({ name });
  },
}));
