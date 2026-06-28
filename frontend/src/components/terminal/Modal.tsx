import { ReactNode, useEffect } from "react";
import { cn } from "@/lib/utils";

/** Centered terminal-styled modal: backdrop click or Escape closes. */
export function Modal({
  title,
  onClose,
  children,
  className,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}) {
  useEffect(() => {
    const down = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-background/80 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div
        className={cn(
          "chat-scroll max-h-[85vh] w-full max-w-xl overflow-y-auto border border-primary/40 bg-card shadow-2xl",
          className,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sticky top-0 flex h-9 items-center justify-between border-b border-border bg-secondary/90 px-3 backdrop-blur">
          <h2 className="micro text-primary">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="font-mono text-sm text-muted-foreground hover:text-foreground"
          >
            ×
          </button>
        </header>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
