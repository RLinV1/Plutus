import { useEffect, useState } from "react";
import { Command } from "cmdk";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";
import { VIEWS, VIEW_LABEL, useWorkspace } from "../../stores/workspace";

/** Ctrl/Cmd+K command palette: jump to any ticker, switch views, run actions.
 *  The keyboard-first heart of the terminal. */
export function CommandPalette({ onAsk }: { onAsk: (q: string) => void }) {
  const open = useWorkspace((s) => s.paletteOpen);
  const setOpen = useWorkspace((s) => s.setPaletteOpen);
  const openTicker = useWorkspace((s) => s.openTicker);
  const setView = useWorkspace((s) => s.setView);
  const [query, setQuery] = useState("");

  const { data: universe = [] } = useQuery({
    queryKey: ["universe"],
    queryFn: api.universe,
    staleTime: Infinity,
  });

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen(!open);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [open, setOpen]);

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const close = () => setOpen(false);
  const q = query.trim();
  const qUpper = q.toUpperCase();
  const inUniverse = universe.some((u) => u.symbol === qUpper);
  const looksLikeTicker = /^[A-Z][A-Z0-9.\-]{0,9}$/.test(qUpper);

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command palette"
      shouldFilter={true}
      className="overflow-hidden border border-primary/40 bg-popover shadow-2xl"
    >
      <Command.Input
        value={query}
        onValueChange={setQuery}
        placeholder="Type a ticker, view, or command…"
        className="h-12 w-full border-b border-border bg-transparent px-4 font-mono text-sm text-foreground outline-none placeholder:text-muted-foreground"
      />
      <Command.List className="chat-scroll max-h-[50vh] overflow-y-auto p-1.5">
        <Command.Empty className="px-3 py-6 text-center font-mono text-xs text-muted-foreground">
          No matches. Type an exact ticker symbol to open it anyway.
        </Command.Empty>

        <Command.Group
          heading="VIEWS"
          className="[&_[cmdk-group-heading]]:micro [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5"
        >
          {VIEWS.map((v, i) => (
            <Item
              key={v}
              onSelect={() => {
                setView(v);
                close();
              }}
            >
              <span className="font-mono text-xs text-primary">{i + 1}</span>
              {VIEW_LABEL[v]}
            </Item>
          ))}
        </Command.Group>

        <Command.Group
          heading="ACTIONS"
          className="[&_[cmdk-group-heading]]:micro [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5"
        >
          <Item
            onSelect={() => {
              setView("portfolio");
              close();
            }}
          >
            ＋ Record a trade…
          </Item>
          <Item
            onSelect={() => {
              setView("scenario");
              close();
            }}
          >
            ⚡ Run a stress test…
          </Item>
          {q.length > 2 && !looksLikeTicker && (
            <Item
              onSelect={() => {
                onAsk(q);
                close();
              }}
            >
              ✦ Ask AI: “{q}”
            </Item>
          )}
        </Command.Group>

        <Command.Group
          heading="TICKERS"
          className="[&_[cmdk-group-heading]]:micro [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5"
        >
          {looksLikeTicker && !inUniverse && (
            <Item
              value={`open-${qUpper}`}
              onSelect={() => {
                openTicker(qUpper);
                close();
              }}
            >
              <span className="w-14 font-mono font-bold">{qUpper}</span>
              <span className="text-muted-foreground">Open ticker</span>
            </Item>
          )}
          {universe.slice(0, 400).map((u) => (
            <Item
              key={u.symbol}
              value={`${u.symbol} ${u.name}`}
              onSelect={() => {
                openTicker(u.symbol);
                close();
              }}
            >
              <span className="w-14 font-mono font-bold">{u.symbol}</span>
              <span className="truncate text-muted-foreground">{u.name}</span>
            </Item>
          ))}
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}

function Item({
  children,
  onSelect,
  value,
}: {
  children: React.ReactNode;
  onSelect: () => void;
  value?: string;
}) {
  return (
    <Command.Item
      value={value}
      onSelect={onSelect}
      className="flex cursor-pointer items-center gap-3 px-2.5 py-2 text-sm aria-selected:bg-primary/15 aria-selected:text-foreground"
    >
      {children}
    </Command.Item>
  );
}
