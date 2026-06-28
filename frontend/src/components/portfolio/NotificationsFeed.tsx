import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import { useStream } from "../../stores/streamStore";
import { useWorkspace } from "../../stores/workspace";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Persisted notifications (from the DB) merged with any that arrived live
 *  over the WebSocket since page load. */
export function NotificationsFeed() {
  const qc = useQueryClient();
  const live = useStream((s) => s.notifications);
  const openTicker = useWorkspace((s) => s.openTicker);
  const { data: stored = [] } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.notifications(false),
    refetchInterval: 60_000,
  });

  const seen = new Set<number>();
  const merged = [...live, ...stored].filter((n) => {
    if (seen.has(n.id)) return false;
    seen.add(n.id);
    return true;
  });

  const markAll = async () => {
    await api.markRead();
    qc.invalidateQueries({ queryKey: ["notifications"] });
  };

  if (!merged.length) {
    return (
      <p className="text-xs text-muted-foreground">
        Nothing yet. Create an alert rule and the feed fills in as conditions
        trigger (checked every ~20s).
      </p>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex justify-end">
        <Button size="sm" variant="ghost" onClick={markAll}>
          Mark all read
        </Button>
      </div>
      <ul className="chat-scroll max-h-80 space-y-1.5 overflow-y-auto">
        {merged.map((n) => (
          <li
            key={n.id}
            className={cn(
              "border border-border/60 px-2.5 py-1.5",
              !n.read && "border-l-2 border-l-primary",
            )}
          >
            <div className="flex items-baseline gap-2">
              {n.ticker && (
                <button
                  className="font-mono text-xs font-bold hover:text-primary"
                  onClick={() => openTicker(n.ticker)}
                >
                  {n.ticker}
                </button>
              )}
              <span className="text-sm">{n.title}</span>
              <span className="ml-auto shrink-0 font-mono text-[0.625rem] text-muted-foreground">
                {n.created_at?.slice(11, 19) ?? ""}
              </span>
            </div>
            {n.body && <p className="mt-0.5 text-xs text-muted-foreground">{n.body}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
