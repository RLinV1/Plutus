import { useEffect } from "react";
import { useStream } from "../../stores/streamStore";
import { useWorkspace } from "../../stores/workspace";
import type { Notification } from "../../types";

/** Alert banners: any notification arriving over the WebSocket shows as an
 *  overlay at the top of the screen for 5 seconds, on every tab. Clicking
 *  opens the Alerts view. */
export function Toasts() {
  const toasts = useStream((s) => s.toasts);
  return (
    <div className="pointer-events-none fixed inset-x-0 top-12 z-[70] flex flex-col items-center gap-2 px-4">
      {toasts.map((t) => (
        <Toast key={t.id} toast={t} />
      ))}
    </div>
  );
}

function Toast({ toast }: { toast: Notification }) {
  const dismiss = useStream((s) => s.dismissToast);
  const setView = useWorkspace((s) => s.setView);

  useEffect(() => {
    const id = window.setTimeout(() => dismiss(toast.id), 5000);
    return () => window.clearTimeout(id);
  }, [toast.id, dismiss]);

  return (
    <button
      onClick={() => {
        dismiss(toast.id);
        setView("alerts");
      }}
      className="toast-in pointer-events-auto flex w-full max-w-xl items-baseline gap-3 border border-primary/60 bg-card/95 px-4 py-2.5 text-left shadow-2xl shadow-black/60 backdrop-blur"
      aria-live="assertive"
    >
      <span className="micro shrink-0 text-primary">⚠ ALERT</span>
      {toast.ticker && (
        <span className="shrink-0 font-mono text-sm font-bold">{toast.ticker}</span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold">{toast.title}</span>
        {toast.body && (
          <span className="block truncate text-xs text-muted-foreground">{toast.body}</span>
        )}
      </span>
      <span
        className="shrink-0 font-mono text-sm text-muted-foreground hover:text-foreground"
        onClick={(e) => {
          e.stopPropagation();
          dismiss(toast.id);
        }}
        role="button"
        aria-label="Dismiss"
      >
        ×
      </span>
    </button>
  );
}
