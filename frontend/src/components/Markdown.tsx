import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Renders the assistant's markdown (GFM: tables, lists, bold, etc.) styled to
 *  match the dark theme. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: (p) => <p className="my-2 first:mt-0 last:mb-0" {...p} />,
          h1: (p) => <h1 className="mb-2 mt-4 text-lg font-bold first:mt-0" {...p} />,
          h2: (p) => <h2 className="mb-2 mt-4 text-base font-bold first:mt-0" {...p} />,
          h3: (p) => (
            <h3
              className="mb-1 mt-4 text-xs font-bold uppercase tracking-wider text-muted-foreground first:mt-0"
              {...p}
            />
          ),
          ul: (p) => <ul className="my-2 list-disc space-y-1 pl-5" {...p} />,
          ol: (p) => <ol className="my-2 list-decimal space-y-1 pl-5" {...p} />,
          li: (p) => <li className="leading-relaxed" {...p} />,
          strong: (p) => <strong className="font-semibold text-foreground" {...p} />,
          em: (p) => <em className="italic" {...p} />,
          a: (p) => (
            <a
              className="text-primary underline underline-offset-2"
              target="_blank"
              rel="noreferrer"
              {...p}
            />
          ),
          blockquote: (p) => (
            <blockquote
              className="my-2 border-l-2 border-primary/50 pl-3 italic text-muted-foreground"
              {...p}
            />
          ),
          hr: () => <hr className="my-3 border-border" />,
          code: (p) => (
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]" {...p} />
          ),
          pre: (p) => (
            <pre
              className="my-2 overflow-x-auto rounded-lg bg-muted p-3 text-xs"
              {...p}
            />
          ),
          table: (p) => (
            <div className="my-3 overflow-x-auto rounded-lg border border-border">
              <table className="w-full border-collapse text-sm" {...p} />
            </div>
          ),
          thead: (p) => <thead className="bg-muted/50" {...p} />,
          th: (p) => (
            <th
              className="border-b border-border px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              {...p}
            />
          ),
          td: (p) => (
            <td className="border-b border-border/50 px-3 py-2 align-top" {...p} />
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
