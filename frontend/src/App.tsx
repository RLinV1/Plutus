import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { ChatWidget } from "./components/terminal/ChatWidget";
import { HelpOverlay } from "./components/terminal/HelpOverlay";
import { Tour } from "./components/terminal/Tour";
import { Toasts } from "./components/terminal/Toasts";
import { SettingsMenu } from "./components/terminal/SettingsMenu";
import { CommandPalette } from "./components/terminal/CommandPalette";
import { applyScale, useSettings } from "./stores/settings";
import { StatusBar } from "./components/terminal/StatusBar";
import { TickerTape } from "./components/terminal/TickerTape";
import { Kbd } from "./components/terminal/Kbd";
import { startStream } from "./lib/ws";
import { useStream } from "./stores/streamStore";
import { VIEWS, VIEW_LABEL, useWorkspace, type View } from "./stores/workspace";
import type { ChatMsg } from "./views/AskView";
import { cn } from "@/lib/utils";

const ResearchView = lazy(() => import("./views/ResearchView"));
const MarketView = lazy(() => import("./views/MarketView"));
const PortfolioView = lazy(() => import("./views/PortfolioView"));
const PaperView = lazy(() => import("./views/PaperView"));
const ScenarioView = lazy(() => import("./views/ScenarioView"));
const AlertsView = lazy(() => import("./views/AlertsView"));
const AskView = lazy(() => import("./views/AskView"));

export default function App() {
  const view = useWorkspace((s) => s.view);
  const ticker = useWorkspace((s) => s.ticker);
  const setView = useWorkspace((s) => s.setView);
  const setPaletteOpen = useWorkspace((s) => s.setPaletteOpen);
  const setTourOpen = useWorkspace((s) => s.setTourOpen);
  const unseen = useStream((s) => s.unseen);
  const clearUnseen = useStream((s) => s.clearUnseen);

  // Chat lives at the shell level so history survives view switches and the
  // palette can hand questions to it from anywhere.
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    startStream();
    applyScale(useSettings.getState().scale);
  }, []);

  // Single-key shortcuts when no input is focused: 1-5 switch views, / opens
  // the universal search (the command palette).
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable)
        return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "/") {
        e.preventDefault();
        setPaletteOpen(true);
        return;
      }
      if (e.key === "?") {
        e.preventDefault();
        setTourOpen(true);
        return;
      }
      const idx = Number(e.key) - 1;
      if (idx >= 0 && idx < VIEWS.length) setView(VIEWS[idx]);
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [setView, setPaletteOpen, setTourOpen]);

  useEffect(() => {
    if (view === "alerts") clearUnseen();
  }, [view, clearUnseen]);

  const ask = async (question: string) => {
    if (!question.trim() || chatBusy) return;
    setChat((c) => [
      ...c,
      { role: "user", text: question },
      { role: "assistant", text: "", tools: [] },
    ]);
    setChatBusy(true);

    let answer = "";
    let tools: string[] = [];
    const update = () =>
      setChat((c) => {
        const copy = [...c];
        copy[copy.length - 1] = { role: "assistant", text: answer, tools: [...tools] };
        return copy;
      });

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const res = await fetch("/api/ask_stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          const ev = JSON.parse(line.slice(5).trim());
          if (ev.type === "tool") tools = [...tools, ev.name];
          else if (ev.type === "text") answer += (answer ? "\n\n" : "") + ev.text;
          else if (ev.type === "error") answer = ev.error;
          update();
        }
      }
      if (!answer) {
        answer = "(no answer)";
        update();
      }
    } catch (e: unknown) {
      answer =
        (e as Error)?.name === "AbortError"
          ? answer
            ? answer + "\n\n_(stopped)_"
            : "_(stopped)_"
          : "Sorry, something went wrong.";
      update();
    } finally {
      abortRef.current = null;
      setChatBusy(false);
    }
  };

  const askAbout = (q: string) => {
    setView("ask");
    ask(q);
  };

  return (
    <div className="flex h-full flex-col">
      {/* Top chrome */}
      <header className="flex h-14 items-center gap-5 border-b border-border bg-card px-4">
        <span className="font-mono text-lg font-bold tracking-tight text-primary">
          ▌PLUTUS
        </span>
        <nav data-tour="nav" className="flex gap-1" aria-label="Views">
          {VIEWS.map((v: View, i) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                "relative px-3 py-2 font-mono text-xs font-bold tracking-wider",
                view === v
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <span className="mr-1 opacity-60">{i + 1}</span>
              {VIEW_LABEL[v]}
              {v === "alerts" && unseen > 0 && (
                <span className="absolute -right-0.5 -top-0.5 grid h-3.5 min-w-3.5 place-items-center rounded-full bg-down px-0.5 text-[0.5625rem] font-bold text-white">
                  {unseen}
                </span>
              )}
            </button>
          ))}
        </nav>
        {/* The ONE search: tickers, views, commands, ask-AI — all via ⌘K. */}
        <button
          data-tour="search"
          onClick={() => setPaletteOpen(true)}
          className="ml-auto hidden h-9 w-72 items-center gap-2 border border-border bg-background px-3 font-mono text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground sm:flex"
          aria-label="Search tickers and commands"
        >
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 shrink-0" aria-hidden="true">
            <path
              d="M21 21l-4.3-4.3M11 19a8 8 0 100-16 8 8 0 000 16z"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          <span className="truncate">Search ticker, view, or command…</span>
          <span className="ml-auto flex gap-1">
            <Kbd>/</Kbd>
            <Kbd>⌘K</Kbd>
          </span>
        </button>
        <SettingsMenu />
      </header>

      <TickerTape />

      <main className="chat-scroll flex-1 overflow-y-auto p-3">
        <Suspense
          fallback={
            <div className="grid h-40 place-items-center font-mono text-xs text-muted-foreground">
              loading view…
            </div>
          }
        >
          {view === "research" && <ResearchView />}
          {view === "market" && <MarketView />}
          {view === "portfolio" && <PortfolioView onAsk={askAbout} />}
          {view === "paper" && <PaperView />}
          {view === "scenario" && <ScenarioView onAsk={askAbout} />}
          {view === "alerts" && <AlertsView />}
          {view === "ask" && (
            <AskView
              msgs={chat}
              busy={chatBusy}
              onSend={ask}
              onStop={() => abortRef.current?.abort()}
            />
          )}
        </Suspense>
      </main>

      <StatusBar />
      <CommandPalette onAsk={askAbout} />
      <HelpOverlay />
      <Tour />
      <Toasts />
      {/* Floating advisor bubble everywhere except the full ASK AI view. */}
      {view !== "ask" && (
        <ChatWidget
          ticker={ticker}
          msgs={chat}
          busy={chatBusy}
          onSend={ask}
          onStop={() => abortRef.current?.abort()}
          onOpenFull={() => setView("ask")}
        />
      )}
    </div>
  );
}
