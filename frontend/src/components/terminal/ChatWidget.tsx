import { useEffect, useRef, useState } from "react";
import { Markdown } from "../Markdown";
import type { ChatMsg } from "../../views/AskView";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

/** Floating chatbot: a bubble in the bottom-right corner that opens a compact
 *  advisor window. Shares the same chat state as the full ASK AI view. */
export function ChatWidget({
  ticker,
  msgs,
  busy,
  onSend,
  onStop,
  onOpenFull,
}: {
  ticker: string;
  msgs: ChatMsg[];
  busy: boolean;
  onSend: (q: string) => void;
  onStop: () => void;
  onOpenFull: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [msgs, busy, open]);

  const send = (q: string) => {
    if (!q.trim() || busy) return;
    onSend(q);
    setInput("");
  };

  const chips = [
    `Why did ${ticker} move recently?`,
    `Is ${ticker} risky?`,
    `How risky is my portfolio?`,
  ];

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label="Open advisor chat"
        data-tour="chatbubble"
        className="fixed bottom-12 right-4 z-40 grid h-12 w-12 place-items-center rounded-full border border-primary/60 bg-card text-primary shadow-lg shadow-black/50 transition-transform hover:scale-105"
      >
        {busy ? (
          <Spinner className="h-5 w-5" />
        ) : (
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden="true">
            <path
              d="M4 5h16v11H9l-5 4V5z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            <path d="M8 9h8M8 12h5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        )}
        {msgs.length > 0 && (
          <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-info" />
        )}
      </button>
    );
  }

  return (
    <div className="fixed bottom-12 right-4 z-40 flex max-h-[70vh] w-[min(380px,calc(100vw-2rem))] flex-col border border-primary/40 bg-card shadow-2xl shadow-black/60">
      <header className="flex h-9 shrink-0 items-center gap-2 border-b border-border bg-secondary/40 px-3">
        <span className="micro text-info">✦ ADVISOR</span>
        <button
          onClick={onOpenFull}
          className="ml-auto font-mono text-[0.625rem] text-muted-foreground hover:text-foreground"
          title="Open the full advisor session"
        >
          FULL ↗
        </button>
        <button
          onClick={() => setOpen(false)}
          aria-label="Close chat"
          className="font-mono text-sm text-muted-foreground hover:text-foreground"
        >
          ×
        </button>
      </header>

      <div ref={scrollRef} className="chat-scroll min-h-32 flex-1 space-y-2 overflow-y-auto p-2.5">
        {msgs.length === 0 && (
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">
              Ask about any stock or your portfolio:
            </p>
            {chips.map((c) => (
              <button
                key={c}
                onClick={() => send(c)}
                className="block w-full border border-border px-2 py-1.5 text-left font-mono text-[0.6875rem] text-muted-foreground hover:border-primary/50 hover:text-foreground"
              >
                {c}
              </button>
            ))}
          </div>
        )}
        {msgs.slice(-8).map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] border border-primary/40 bg-primary/10 px-2.5 py-1.5 font-mono text-[0.6875rem]">
                {m.text}
              </div>
            </div>
          ) : (
            <div key={i} className="border border-border bg-background/60 p-2 text-[0.8125rem]">
              <Markdown>{m.text}</Markdown>
            </div>
          ),
        )}
        {busy && (
          <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
            <Spinner className="h-3.5 w-3.5" /> working…
          </div>
        )}
      </div>

      <div className="flex shrink-0 gap-1.5 border-t border-border p-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send(input);
            if (e.key === "Escape") setOpen(false);
          }}
          placeholder={`Ask about ${ticker}…`}
          autoFocus
          className="h-8 min-w-0 flex-1 border border-input bg-background px-2 font-mono text-xs outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
        />
        {busy ? (
          <Button size="sm" variant="secondary" onClick={onStop} aria-label="Stop">
            ■
          </Button>
        ) : (
          <Button size="sm" onClick={() => send(input)} disabled={!input.trim()}>
            Send
          </Button>
        )}
      </div>
    </div>
  );
}
