import { useEffect, useRef, useState } from "react";
import { UI_SCALES, useSettings } from "../../stores/settings";
import { useWorkspace } from "../../stores/workspace";
import { cn } from "@/lib/utils";

/** Header gear: user-experience settings (UI size now; room to grow). */
export function SettingsMenu() {
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const scale = useSettings((s) => s.scale);
  const setScale = useSettings((s) => s.setScale);
  const setHelpOpen = useWorkspace((s) => s.setHelpOpen);
  const setBillingOpen = useWorkspace((s) => s.setBillingOpen);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <div className="relative" ref={boxRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Settings"
        aria-expanded={open}
        title="Settings — adjust UI size"
        className={cn(
          "grid h-9 w-9 place-items-center border border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
          open && "border-primary/60 text-primary",
        )}
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden="true">
          <path
            d="M12 15a3 3 0 100-6 3 3 0 000 6z"
            stroke="currentColor"
            strokeWidth="2"
          />
          <path
            d="M19.4 15a1.7 1.7 0 00.34 1.87l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.7 1.7 0 00-1.87-.34 1.7 1.7 0 00-1.03 1.56V21a2 2 0 11-4 0v-.09a1.7 1.7 0 00-1.11-1.56 1.7 1.7 0 00-1.87.34l-.06.06a2 2 0 11-2.83-2.83l.06-.06A1.7 1.7 0 004.6 15a1.7 1.7 0 00-1.56-1.03H3a2 2 0 110-4h.09A1.7 1.7 0 004.65 8.9a1.7 1.7 0 00-.34-1.87l-.06-.06A2 2 0 117.08 4.14l.06.06a1.7 1.7 0 001.87.34h.08A1.7 1.7 0 0010.12 3V3a2 2 0 114 0v.09c0 .67.4 1.28 1.03 1.55h.08a1.7 1.7 0 001.87-.34l.06-.06a2 2 0 112.83 2.83l-.06.06a1.7 1.7 0 00-.34 1.87v.08c.27.63.88 1.04 1.55 1.04H21a2 2 0 110 4h-.09c-.67 0-1.28.4-1.51 1.03z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-40 w-64 border border-border bg-popover p-2 shadow-2xl">
          <div className="micro mb-1.5 px-1 text-primary">UI SIZE</div>
          <div className="space-y-0.5">
            {UI_SCALES.map((s) => (
              <button
                key={s.value}
                onClick={() => setScale(s.value)}
                className={cn(
                  "flex w-full items-baseline gap-2 px-2 py-1.5 text-left font-mono text-xs",
                  scale === s.value
                    ? "bg-primary/15 text-primary"
                    : "text-foreground hover:bg-accent",
                )}
                aria-pressed={scale === s.value}
              >
                <span className="w-24 font-bold">{s.label}</span>
                <span className="text-muted-foreground">{s.hint}</span>
                {scale === s.value && <span className="ml-auto">✓</span>}
              </button>
            ))}
          </div>
          <div className="mt-2 space-y-0.5 border-t border-border pt-2">
            <button
              onClick={() => {
                setBillingOpen(true);
                setOpen(false);
              }}
              className="w-full px-2 py-1.5 text-left font-mono text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              ✦ Plans &amp; billing
            </button>
            <button
              onClick={() => {
                useWorkspace.getState().setTourOpen(true);
                setOpen(false);
              }}
              className="w-full px-2 py-1.5 text-left font-mono text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              ▶ Take the guided tour
            </button>
            <button
              onClick={() => {
                setHelpOpen(true);
                setOpen(false);
              }}
              className="w-full px-2 py-1.5 text-left font-mono text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              ? Written reference guide
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
