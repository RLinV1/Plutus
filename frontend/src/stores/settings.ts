import { create } from "zustand";

/** User-experience settings. UI scale works by changing the root font-size —
 *  Tailwind sizes are rem-based, so the entire workspace (text, paddings,
 *  panel heights) scales together. Persisted across sessions. */
const KEY = "st.uiScale";

export const UI_SCALES = [
  { value: 1.0, label: "Compact", hint: "dense, classic terminal" },
  { value: 1.15, label: "Comfortable", hint: "default" },
  { value: 1.3, label: "Large", hint: "easier reading" },
  { value: 1.45, label: "Extra large", hint: "maximum legibility" },
] as const;

const DEFAULT_SCALE = 1.15;

function load(): number {
  const raw = Number(localStorage.getItem(KEY));
  return UI_SCALES.some((s) => s.value === raw) ? raw : DEFAULT_SCALE;
}

export function applyScale(scale: number): void {
  document.documentElement.style.fontSize = `${scale * 100}%`;
}

interface SettingsState {
  scale: number;
  setScale: (s: number) => void;
}

export const useSettings = create<SettingsState>((set) => ({
  scale: load(),
  setScale: (scale) => {
    try {
      localStorage.setItem(KEY, String(scale));
    } catch {
      /* non-fatal */
    }
    applyScale(scale);
    set({ scale });
  },
}));
