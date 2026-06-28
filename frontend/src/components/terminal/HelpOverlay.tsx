import { useEffect, useState } from "react";
import { useWorkspace } from "../../stores/workspace";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Kbd } from "./Kbd";

const SEEN_KEY = "st.helpSeen";

interface GuideSection {
  heading: string;
  body: React.ReactNode;
}

interface GuidePage {
  id: string;
  label: string;
  intro: string;
  sections: GuideSection[];
}

/** Detailed, per-page walkthrough: one tab per view, each walking through its
 *  sections top to bottom. Auto-opens on first visit; reopens via `?` or the
 *  status-bar / settings buttons. */
const PAGES: GuidePage[] = [
  {
    id: "basics",
    label: "BASICS",
    intro: "The three things to learn first.",
    sections: [
      {
        heading: "The universal search",
        body: (
          <>
            Press <Kbd>/</Kbd> or <Kbd>Ctrl K</Kbd> anywhere. Type a ticker (or company
            name) to open it, a view name to switch, or a question to send to the AI —
            one box does all three.
          </>
        ),
      },
      {
        heading: "Switching views",
        body: (
          <>
            Keys <Kbd>1</Kbd>–<Kbd>7</Kbd> jump between the seven views in the top bar.
            The number next to each view name is its key.
          </>
        ),
      },
      {
        heading: "The ticker tape",
        body: (
          <>
            The scrolling strip under the top bar carries live prices: market staples
            plus whatever you hold or have alerts on, refreshed about every 20 seconds.
            Hover to pause it (the tooltip shows the quote time); click any ticker to
            open it in Research.
          </>
        ),
      },
      {
        heading: "The advisor bubble",
        body: (
          <>
            The ✦ button in the bottom-right corner opens the AI advisor anywhere in the
            app. It can read live data, the news, and your portfolio — but it can never
            change anything. The full conversation lives in ASK AI (key <Kbd>7</Kbd>).
          </>
        ),
      },
    ],
  },
  {
    id: "research",
    label: "RESEARCH",
    intro: "One stock at a time: price, fundamentals, news.",
    sections: [
      {
        heading: "Quote panel (left)",
        body: (
          <>
            The current price and day move, plus the fundamentals: market cap, P/E
            (price ÷ yearly earnings), volatility profile, RSI (a 0–100 momentum gauge —
            70+ ran up fast, 30− beaten down), the 50/200-day averages, the 52-week
            range, and beta (how hard it moves when the whole market moves).
          </>
        ),
      },
      {
        heading: "Price chart",
        body: (
          <>
            Each candle is one day: green closed higher than it opened, red lower.
            Hover anywhere to read that day's exact open/high/low/close and volume in
            the legend. The amber line is the 50-day average, cyan the 200-day; the
            bars along the bottom are volume. The 1M–ALL buttons change the window.
          </>
        ),
      },
      {
        heading: "Headlines",
        body: <>Recent news for the ticker, dated, with the source on the right. Click to read.</>,
      },
    ],
  },
  {
    id: "portfolio",
    label: "PORTFOLIO",
    intro: "Your real holdings, tracked from your own buys and sells.",
    sections: [
      {
        heading: "MY PORTFOLIO vs DEMO tabs",
        body: (
          <>
            MY PORTFOLIO is yours and starts empty. DEMO holds sample positions so you
            can explore every panel first — it restores itself automatically if wiped,
            and never mixes with your data.
          </>
        ),
      },
      {
        heading: "Holdings table",
        body: (
          <>
            One row per position: shares, average cost, live price, today's move, value,
            weight, and profit/loss (green up, red down). The red SELL button preloads
            the trade form with that position — adjust the shares and confirm.
          </>
        ),
      },
      {
        heading: "Record a trade (right rail)",
        body: (
          <>
            Pick BUY or SELL, search the ticker by name, enter shares and the price you
            paid. Trades are recorded as of today. In SELL mode the search only offers
            what you actually own.
          </>
        ),
      },
      {
        heading: "Bulk import",
        body: (
          <>
            “Import brokerage CSV…” opens a window where you paste or choose your
            broker's export. <b>Preview</b> shows exactly what was understood (and which
            lines weren't) before anything is written; <i>Example</i> shows the format.
          </>
        ),
      },
      {
        heading: "Equity curve, allocation, correlation, risk report",
        body: (
          <>
            The equity curve is your account's value over time. Allocation shows where
            the money sits. The correlation grid shows which holdings move together
            (brighter = more in lockstep — less diversification than it looks). The
            risk report turns it all into numbers, each translated to plain English.
          </>
        ),
      },
      {
        heading: "Danger zone",
        body: (
          <>
            Reset wipes every transaction in the selected portfolio. You must type the
            portfolio's name in the confirmation window — there is no undo.
          </>
        ),
      },
    ],
  },
  {
    id: "paper",
    label: "PAPER TRADE",
    intro: "Practice with $100,000 of pretend money at real prices.",
    sections: [
      {
        heading: "Account strip",
        body: (
          <>
            Cash left, what your positions are worth at live prices, the total, and
            your % return since the start.
          </>
        ),
      },
      {
        heading: "Market order ticket",
        body: (
          <>
            Search a ticker, enter shares, and the ticket shows the live price and your
            estimated cost before you commit. Fills execute at the real current quote.
            Buys beyond your cash and sells beyond your position are rejected.
          </>
        ),
      },
      {
        heading: "Positions & fills",
        body: (
          <>
            Positions work like the portfolio table (including quick SELL); every
            simulated fill is listed below. “Reset paper account…” starts you over —
            type PAPER to confirm.
          </>
        ),
      },
    ],
  },
  {
    id: "scenario",
    label: "SCENARIO LAB",
    intro: "Stress tests and experiments — nothing here is ever saved.",
    sections: [
      {
        heading: "RUN AGAINST selector",
        body: (
          <>
            Choose what to stress: MY PORTFOLIO, DEMO, or a CUSTOM BASKET. The basket
            builder lets you add tickers by search, set a dollar amount on each
            (default $10,000), and remove with ×.
          </>
        ),
      },
      {
        heading: "Stress test",
        body: (
          <>
            Pick a crisis (2008, COVID, the 2022 rate shock…) and see the estimated
            hit: each holding is assumed to move beta × the market's drop in that
            crisis. It's a first-order estimate, not a prediction — the “vs typical bad
            day” number puts it in context against your normal daily risk.
          </>
        ),
      },
      {
        heading: "What-if trade",
        body: (
          <>
            Simulate buying or selling N shares and compare risk before vs after —
            volatility, beta, Sharpe, VaR, concentration. Nothing is recorded.
          </>
        ),
      },
      {
        heading: "Rebalance",
        body: (
          <>
            The trades that would bring the selected portfolio back to equal weight,
            ignoring taxes and fees. A teaching aid for thinking about drift.
          </>
        ),
      },
    ],
  },
  {
    id: "alerts",
    label: "ALERTS",
    intro: "Tripwires checked every ~20 seconds while the backend runs.",
    sections: [
      {
        heading: "New tripwire",
        body: (
          <>
            Pick a rule type (price above/below a level, a daily move bigger than X%,
            RSI hot/cold, a drawdown off the recent high, unusual news volume), a
            ticker, and the threshold, then “Arm it”.
          </>
        ),
      },
      {
        heading: "Armed rules",
        body: (
          <>
            The toggle pauses a rule without deleting it; × deletes it (its past
            notifications are kept). After firing, a rule stays quiet for its cooldown
            (4h by default) so you aren't spammed while the condition holds.
          </>
        ),
      },
      {
        heading: "Notifications",
        body: (
          <>
            Every trigger lands here AND pushes live to the badge on the ALERTS tab.
            Click a ticker to jump to its research page; “Mark all read” clears the
            unread bars.
          </>
        ),
      },
    ],
  },
  {
    id: "ask",
    label: "ASK AI",
    intro: "The advisor, full-screen, with the whole conversation.",
    sections: [
      {
        heading: "What it can do",
        body: (
          <>
            Ask about any stock (“why did NVDA drop this week?”), concepts (“what is a
            P/E ratio?”), or your own portfolio (“how risky is my portfolio?”, “give me
            my briefing”). It pulls live data, news, SEC filings, and the knowledge
            library, and cites where things came from — the small tags above each
            answer show which tools it used.
          </>
        ),
      },
      {
        heading: "What it can't do",
        body: (
          <>
            It reads your portfolio but can never change it — every trade and import
            goes through the forms, never through the AI. Everything is educational
            information, not personalized investment advice.
          </>
        ),
      },
    ],
  },
];

export function HelpOverlay() {
  const open = useWorkspace((s) => s.helpOpen);
  const setOpen = useWorkspace((s) => s.setHelpOpen);
  const [page, setPage] = useState("basics");

  // First-visit onboarding is handled by the interactive Tour; this overlay
  // is the written reference, opened from the settings menu.
  const close = () => setOpen(false);

  useEffect(() => {
    if (!open) return;
    const down = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;
  const active = PAGES.find((p) => p.id === page) ?? PAGES[0];

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-background/80 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Help guide"
      onClick={close}
    >
      <div
        className="flex h-[min(640px,85vh)] w-full max-w-3xl flex-col border border-primary/40 bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex h-9 shrink-0 items-center justify-between border-b border-border bg-secondary/40 px-3">
          <h2 className="micro text-primary">PLUTUS GUIDE — HOW EACH PAGE WORKS</h2>
          <button
            onClick={close}
            aria-label="Close help"
            className="grid h-6 w-6 place-items-center font-mono text-base text-muted-foreground hover:text-foreground"
          >
            ×
          </button>
        </header>

        <div className="flex shrink-0 flex-wrap gap-1 border-b border-border p-2">
          {PAGES.map((p) => (
            <button
              key={p.id}
              onClick={() => setPage(p.id)}
              className={cn(
                "border px-2.5 py-1.5 font-mono text-[0.6875rem] font-bold tracking-wider",
                page === p.id
                  ? "border-primary bg-primary/15 text-primary"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="chat-scroll flex-1 overflow-y-auto p-4">
          <p className="mb-3 text-sm font-semibold text-foreground">{active.intro}</p>
          <div className="space-y-4">
            {active.sections.map((s) => (
              <div key={s.heading}>
                <h3 className="micro mb-1 text-primary">{s.heading.toUpperCase()}</h3>
                <p className="text-sm leading-relaxed text-foreground/85">{s.body}</p>
              </div>
            ))}
          </div>
        </div>

        <footer className="flex shrink-0 items-center justify-between border-t border-border p-3">
          <span className="font-mono text-[0.6875rem] text-muted-foreground">
            Reopen anytime with <Kbd>?</Kbd> · educational, not investment advice
          </span>
          <Button onClick={close}>Got it — let's go</Button>
        </footer>
      </div>
    </div>
  );
}
