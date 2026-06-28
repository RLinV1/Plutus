import { useEffect, useState } from "react";
import { usePortfolio } from "../../stores/portfolioStore";
import { useWorkspace, type View } from "../../stores/workspace";
import { Button } from "@/components/ui/button";
import { Kbd } from "./Kbd";

const SEEN_KEY = "st.tourSeen";

interface TourStep {
  view: View;
  selector: string;
  quote: string;
  text: string;
  /** Runs before the step renders (e.g. flip to the demo portfolio). */
  prep?: () => void;
}

/** The walkthrough: a spotlight on each section of each page, with a one-line
 *  quote and a plain-English explanation pinned next to it. */
const STEPS: TourStep[] = [
  {
    view: "research",
    selector: "[data-tour=nav]",
    quote: "“Seven rooms, one keyboard.”",
    text: "These are the seven views. The number next to each name is its hotkey — press 1 through 7 to jump.",
  },
  {
    view: "research",
    selector: "[data-tour=search]",
    quote: "“Type anywhere, find anything.”",
    text: "The one search box: a ticker or company opens it, a view name switches to it, anything else can go to the AI. Press / or Ctrl+K from anywhere.",
  },
  {
    view: "research",
    selector: "[data-tour=tape]",
    quote: "“The market, drifting by.”",
    text: "Live prices, refreshed about every 20 seconds — market staples plus whatever you hold or alert on. Hover to pause, click a ticker to open it.",
  },
  {
    view: "research",
    selector: "[data-tour=quote]",
    quote: "“The vitals, at a glance.”",
    text: "Price, today's move, and the fundamentals: market cap, P/E, RSI, the moving averages, the 52-week range, and beta.",
  },
  {
    view: "research",
    selector: "[data-tour=chart]",
    quote: "“Hover any day for its story.”",
    text: "Each candle is one day — green closed up, red closed down. Move your cursor across the chart and the legend reads out that day's open, high, low, close, and volume. Amber line = 50-day average, cyan = 200-day.",
  },
  {
    view: "research",
    selector: "[data-tour=news]",
    quote: "“Why prices moved.”",
    text: "Recent headlines for this ticker, dated, with sources. Click any to read the article.",
  },
  {
    view: "portfolio",
    selector: "[data-tour=ptabs]",
    quote: "“Yours, and the sandbox.”",
    text: "MY PORTFOLIO is your real record and starts empty. DEMO is sample data for exploring — we've flipped to it so the next panels have something to show.",
    prep: () => usePortfolio.getState().setName("demo"),
  },
  {
    view: "portfolio",
    selector: "[data-tour=holdings]",
    quote: "“Your scoreboard.”",
    text: "Every position with live price, weight, and profit/loss. The red SELL button preloads the trade form with that position — one click, adjust, confirm.",
  },
  {
    view: "portfolio",
    selector: "[data-tour=trade]",
    quote: "“Record reality here.”",
    text: "Buys and sells you actually made. Search the ticker by name; in SELL mode the search only offers what you own.",
  },
  {
    view: "portfolio",
    selector: "[data-tour=import]",
    quote: "“Bring your history.”",
    text: "Import your broker's CSV export. You always see a preview of exactly what was understood before anything is written.",
  },
  {
    view: "portfolio",
    selector: "[data-tour=danger]",
    quote: "“The big red lever.”",
    text: "Wipes every transaction in the selected portfolio. You must type its name to confirm — and there is no undo.",
  },
  {
    view: "paper",
    selector: "[data-tour=paper-account]",
    quote: "“$100,000 of consequence-free.”",
    text: "The paper account: pretend cash, real prices. Practice trading without risking anything.",
  },
  {
    view: "paper",
    selector: "[data-tour=paper-ticket]",
    quote: "“Orders fill at the real quote.”",
    text: "Pick a ticker and shares — the ticket shows the live price and estimated cost before you commit. Overspending and overselling are rejected.",
  },
  {
    view: "scenario",
    selector: "[data-tour=stress]",
    quote: "“Rehearse the crash.”",
    text: "Pick a historical crisis and see the estimated hit to the selected portfolio — each holding moves beta × the market's drop. An estimate for scale, not a prediction.",
  },
  {
    view: "scenario",
    selector: "[data-tour=whatif]",
    quote: "“Try the trade before you make it.”",
    text: "Simulate a buy or sell and compare risk before vs after. Nothing is saved — it's a sandbox.",
  },
  {
    view: "alerts",
    selector: "[data-tour=alert-new]",
    quote: "“Set tripwires.”",
    text: "Price levels, big daily moves, RSI extremes, drawdowns, news spikes. Rules are checked every ~20 seconds while the backend runs.",
  },
  {
    view: "alerts",
    selector: "[data-tour=notifications]",
    quote: "“They find you.”",
    text: "Every trigger lands here and on the ALERTS badge, live. After firing, a rule cools down (4h default) so it can't spam you.",
  },
  {
    view: "research",
    selector: "[data-tour=chatbubble]",
    quote: "“Your advisor lives here.”",
    text: "Ask anything — a stock, a concept, or your own portfolio. It reads your data and cites its sources, but can never change anything. That's the whole tour: reopen it anytime with ?",
  },
];

export function Tour() {
  const open = useWorkspace((s) => s.tourOpen);
  const setOpen = useWorkspace((s) => s.setTourOpen);
  const setView = useWorkspace((s) => s.setView);
  const [idx, setIdx] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  // First-ever visit: start the tour automatically.
  useEffect(() => {
    if (!localStorage.getItem(SEEN_KEY)) setOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const close = () => {
    try {
      localStorage.setItem(SEEN_KEY, "1");
    } catch {
      /* non-fatal */
    }
    setOpen(false);
    setIdx(0);
  };

  // On step change: switch view, wait for the (lazy) view to render the
  // target, scroll it into view, and measure it.
  useEffect(() => {
    if (!open) return;
    const step = STEPS[idx];
    step.prep?.();
    setView(step.view);
    setRect(null);
    let tries = 0;
    let raf = 0;
    let cancelled = false;
    const find = () => {
      if (cancelled) return;
      const el = document.querySelector(step.selector) as HTMLElement | null;
      if (el && el.getBoundingClientRect().width > 0) {
        el.scrollIntoView({ block: "center" });
        requestAnimationFrame(() => {
          if (!cancelled) setRect(el.getBoundingClientRect());
        });
      } else if (tries++ < 60) {
        raf = requestAnimationFrame(find);
      }
    };
    find();
    const remeasure = () => {
      const el = document.querySelector(step.selector);
      if (el) setRect(el.getBoundingClientRect());
    };
    window.addEventListener("resize", remeasure);
    // Panels grow as their data loads — keep the spotlight glued to the
    // section while the step is showing.
    const follow = window.setInterval(remeasure, 400);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", remeasure);
      window.clearInterval(follow);
    };
  }, [open, idx, setView]);

  useEffect(() => {
    if (!open) return;
    const down = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight" || e.key === "Enter")
        setIdx((i) => Math.min(i + 1, STEPS.length - 1));
      if (e.key === "ArrowLeft") setIdx((i) => Math.max(i - 1, 0));
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;
  const step = STEPS[idx];
  const last = idx === STEPS.length - 1;

  // Popover below the target when there's room, above otherwise.
  const pad = 8;
  const popoverW = 380;
  let popStyle: React.CSSProperties = {
    left: "50%",
    top: "40%",
    transform: "translateX(-50%)",
  };
  if (rect) {
    const below = rect.bottom + 220 < window.innerHeight;
    const left = Math.min(
      Math.max(rect.left, 12),
      window.innerWidth - popoverW - 12,
    );
    popStyle = below
      ? { left, top: rect.bottom + pad + 4 }
      : { left, bottom: window.innerHeight - rect.top + pad + 4 };
  }

  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label="Guided tour">
      {/* Spotlight: the hole is the target; everything else dims. */}
      {rect ? (
        <div
          className="pointer-events-none fixed border-2 border-primary transition-all duration-200"
          style={{
            left: rect.left - pad,
            top: rect.top - pad,
            width: rect.width + pad * 2,
            height: rect.height + pad * 2,
            boxShadow: "0 0 0 9999px hsl(40 14% 4% / 0.82)",
          }}
        />
      ) : (
        <div className="pointer-events-none fixed inset-0 bg-background/82" />
      )}

      {/* The caption card pinned to the section. */}
      <div
        className="fixed z-[61] border border-primary/50 bg-card p-3.5 shadow-2xl"
        style={{ ...popStyle, width: popoverW, maxWidth: "calc(100vw - 24px)" }}
      >
        <p className="font-mono text-sm font-bold text-primary">{step.quote}</p>
        <p className="mt-1.5 text-sm leading-relaxed text-foreground/90">{step.text}</p>
        <div className="mt-3 flex items-center gap-2">
          <span className="font-mono text-[0.6875rem] text-muted-foreground">
            {idx + 1} / {STEPS.length}
          </span>
          <span className="hidden font-mono text-[0.625rem] text-muted-foreground/60 sm:inline">
            <Kbd>←</Kbd> <Kbd>→</Kbd> to move
          </span>
          <div className="ml-auto flex gap-1.5">
            <Button size="sm" variant="ghost" onClick={close}>
              Skip
            </Button>
            {idx > 0 && (
              <Button size="sm" variant="outline" onClick={() => setIdx((i) => i - 1)}>
                ← Back
              </Button>
            )}
            {last ? (
              <Button size="sm" onClick={close}>
                Done ✓
              </Button>
            ) : (
              <Button size="sm" onClick={() => setIdx((i) => i + 1)}>
                Next →
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
