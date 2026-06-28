import { create } from "zustand";
import type { Notification, QuoteMap } from "../types";

export type WsStatus = "connecting" | "open" | "closed";

interface StreamState {
  status: WsStatus;
  quotes: QuoteMap;
  /** Local wall-clock time each ticker's quote last arrived (HH:MM:SS). */
  quotedAt: Record<string, string>;
  /** Tick direction of the latest update per ticker, for flash animations. */
  lastTick: Record<string, "up" | "down">;
  notifications: Notification[];
  /** Notifications that arrived live and haven't finished their 5s banner. */
  toasts: Notification[];
  unseen: number;
  setStatus: (s: WsStatus) => void;
  applyQuotes: (q: QuoteMap) => void;
  pushNotification: (n: Notification) => void;
  dismissToast: (id: number) => void;
  seedNotifications: (ns: Notification[]) => void;
  clearUnseen: () => void;
}

export const useStream = create<StreamState>((set) => ({
  status: "connecting",
  quotes: {},
  quotedAt: {},
  lastTick: {},
  notifications: [],
  toasts: [],
  unseen: 0,
  setStatus: (status) => set({ status }),
  applyQuotes: (incoming) =>
    set((s) => {
      const lastTick: Record<string, "up" | "down"> = {};
      const now = new Date().toLocaleTimeString([], { hour12: false });
      const quotedAt = { ...s.quotedAt };
      for (const [t, q] of Object.entries(incoming)) {
        quotedAt[t] = now;
        const prev = s.quotes[t]?.price;
        if (prev != null && q.price != null && q.price !== prev) {
          lastTick[t] = q.price > prev ? "up" : "down";
        }
      }
      return { quotes: { ...s.quotes, ...incoming }, lastTick, quotedAt };
    }),
  pushNotification: (n) =>
    set((s) => ({
      notifications: [n, ...s.notifications].slice(0, 100),
      toasts: [...s.toasts, n].slice(-3),
      unseen: s.unseen + 1,
    })),
  dismissToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  seedNotifications: (ns) => set({ notifications: ns }),
  clearUnseen: () => set({ unseen: 0 }),
}));
