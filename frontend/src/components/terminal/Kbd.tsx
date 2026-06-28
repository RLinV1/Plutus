import { ReactNode } from "react";

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center border border-border bg-secondary px-1 font-mono text-[0.625rem] font-bold text-muted-foreground">
      {children}
    </kbd>
  );
}
