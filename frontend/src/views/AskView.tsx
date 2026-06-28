import { useEffect, useRef, useState } from "react";
import { Markdown } from "../components/Markdown";
import { Panel } from "../components/terminal/Panel";
import { useWorkspace } from "../stores/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";

export interface ChatMsg {
  role: "user" | "assistant";
  text: string;
  tools?: string[];
}

export default function AskView({
  msgs,
  busy,
  onSend,
  onStop,
}: {
  msgs: ChatMsg[];
  busy: boolean;
  onSend: (q: string) => void;
  onStop: () => void;
}) {
  const ticker = useWorkspace((s) => s.ticker);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const starters = [
    `Give me my portfolio briefing for today`,
    `How risky is my portfolio?`,
    `How would my portfolio handle a 2008-style crash?`,
    `What's the news on ${ticker} — good or bad?`,
    `What would buying 10 shares of ${ticker} do to my portfolio?`,
  ];

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [msgs, busy]);

  const submit = () => {
    if (!input.trim()) return;
    onSend(input);
    setInput("");
  };

  return (
    <Panel title="ADVISOR SESSION" bodyClassName="p-0">
      <div className="flex h-[calc(100vh-220px)] min-h-[420px] flex-col p-3">
        <div ref={scrollRef} className="chat-scroll flex-1 space-y-3 overflow-y-auto pr-2">
          {msgs.length === 0 && (
            <div className="text-sm text-muted-foreground">
              <p className="mb-3">
                Ask in plain English. The advisor reads live data, the news, the
                knowledge library — and YOUR portfolio (read-only: it can analyze
                it, never change it).
              </p>
              <div className="flex flex-wrap gap-2">
                {starters.map((s) => (
                  <Button key={s} variant="outline" size="sm" onClick={() => onSend(s)}>
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[85%] border border-primary/40 bg-primary/10 px-3 py-2 font-mono text-[0.8125rem]">
                  {m.text}
                </div>
              </div>
            ) : (
              <div key={i} className="border border-border bg-background/50 p-3">
                <div className="mb-2 flex items-center gap-2">
                  <span className="micro text-info">✦ ADVISOR</span>
                  {m.tools && m.tools.length > 0 && (
                    <span className="ml-auto flex flex-wrap justify-end gap-1">
                      {m.tools.map((t, j) => (
                        <span
                          key={`${t}-${j}`}
                          className="border border-border bg-secondary px-1.5 py-0.5 font-mono text-[0.625rem] text-muted-foreground"
                        >
                          {t}
                        </span>
                      ))}
                    </span>
                  )}
                </div>
                <Markdown>{m.text}</Markdown>
              </div>
            ),
          )}
          {busy && (
            <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
              <Spinner className="h-4 w-4" />
              working…
            </div>
          )}
        </div>

        <div className="mt-3 flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !busy && submit()}
            placeholder={`Ask about ${ticker} or your portfolio…`}
            className="font-mono"
          />
          {busy ? (
            <Button onClick={onStop} variant="secondary" className="min-w-[84px]">
              ■ Stop
            </Button>
          ) : (
            <Button onClick={submit} className="min-w-[84px]">
              Send
            </Button>
          )}
        </div>
      </div>
    </Panel>
  );
}
