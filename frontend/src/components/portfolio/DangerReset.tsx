import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

/** Type-to-confirm destructive action, presented as a blocking modal: the
 *  wipe button only arms after the user types the exact required text
 *  (GitHub-style), so a stray click can never destroy anything. */
export function DangerReset({
  requiredText,
  warning,
  buttonLabel = "Reset…",
  onConfirm,
}: {
  requiredText: string;
  warning: string;
  buttonLabel?: string;
  /** Receives the user's typed confirmation so the server can verify it too. */
  onConfirm: (typed: string) => Promise<string>;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [modalMsg, setModalMsg] = useState("");

  const armed = text.trim().toUpperCase() === requiredText.toUpperCase();

  const close = () => {
    setOpen(false);
    setText("");
    setModalMsg("");
  };

  useEffect(() => {
    if (!open) return;
    const down = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const run = async () => {
    if (!armed || busy) return;
    setBusy(true);
    setModalMsg("");
    try {
      setMsg(await onConfirm(text.trim()));
      close();
    } catch (e) {
      setModalMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <Button
        variant="outline"
        size="sm"
        className="w-full border-down/40 text-down hover:bg-down/10"
        onClick={() => {
          setOpen(true);
          setMsg("");
        }}
      >
        {buttonLabel}
      </Button>
      {msg && <p className="mt-1.5 font-mono text-[0.6875rem] text-muted-foreground">{msg}</p>}

      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-background/80 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm reset"
          onClick={close}
        >
          <div
            className="w-full max-w-md border border-down/60 bg-card shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="flex h-9 items-center justify-between border-b border-down/40 bg-down/10 px-3">
              <h2 className="micro text-down">⚠ DANGER — THIS CANNOT BE UNDONE</h2>
              <button
                onClick={close}
                aria-label="Cancel"
                className="font-mono text-sm text-muted-foreground hover:text-foreground"
              >
                ×
              </button>
            </header>
            <div className="space-y-3 p-4">
              <p className="text-sm leading-relaxed text-foreground/90">{warning}</p>
              <p className="font-mono text-[0.6875rem] text-muted-foreground">
                Type{" "}
                <span className="font-bold text-down">{requiredText.toUpperCase()}</span>{" "}
                to confirm:
              </p>
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && run()}
                placeholder={requiredText.toUpperCase()}
                autoFocus
                aria-label={`Type ${requiredText.toUpperCase()} to confirm`}
                className="h-9 w-full border border-down/50 bg-background px-2 font-mono text-sm uppercase outline-none placeholder:text-muted-foreground/50 focus-visible:ring-1 focus-visible:ring-down"
              />
              {modalMsg && (
                <p className="font-mono text-[0.6875rem] text-down">{modalMsg}</p>
              )}
              <div className="flex gap-2">
                <Button
                  className="flex-1 bg-down text-white hover:bg-down/85 disabled:opacity-40"
                  disabled={!armed || busy}
                  onClick={run}
                >
                  {busy ? "Wiping…" : "I understand — wipe it"}
                </Button>
                <Button variant="ghost" onClick={close}>
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
