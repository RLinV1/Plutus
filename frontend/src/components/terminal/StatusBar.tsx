import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";
import { useStream } from "../../stores/streamStore";
import { useWorkspace } from "../../stores/workspace";
import { cn } from "@/lib/utils";
import { Kbd } from "./Kbd";

/** Bottom chrome: live clock, stream state, data mode — the facts a terminal
 *  operator actually checks. */
export function StatusBar() {
  const status = useStream((s) => s.status);
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 60_000,
  });

  return (
    <footer className="flex h-7 items-center gap-4 border-t border-border bg-card px-3 font-mono text-[0.6875rem] text-muted-foreground">
      <span className="flex items-center gap-1.5">
        <span
          className={cn(
            "inline-block h-1.5 w-1.5 rounded-full",
            status === "open" ? "bg-up" : status === "connecting" ? "bg-primary" : "bg-down",
          )}
        />
        {status === "open" ? "STREAM LIVE" : status === "connecting" ? "CONNECTING" : "STREAM DOWN"}
      </span>
      <span>{health ? (health.live_data ? "DATA: LIVE" : "DATA: MOCK") : "DATA: …"}</span>
      <span className="ml-auto hidden items-center gap-1.5 sm:flex">
        <Kbd>⌘K</Kbd> commands · <Kbd>1</Kbd>–<Kbd>7</Kbd> views
      </span>
      <button
        onClick={() => useWorkspace.getState().setTourOpen(true)}
        aria-label="Start the guided tour"
        title="Guided tour (?)"
        className="grid h-5 w-5 place-items-center border border-border font-mono text-[0.625rem] font-bold text-muted-foreground hover:border-primary/50 hover:text-primary"
      >
        ?
      </button>
      <span className="tnum">{now.toLocaleTimeString([], { hour12: false })}</span>
      <span className="hidden text-muted-foreground/70 md:inline">educational · not advice</span>
    </footer>
  );
}
