import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

function formatLocations(locations) {
  if (!locations?.length) return null;
  return locations.join(", ");
}

function ContextItem({ ctx, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const loc = formatLocations(ctx.locations);
  const title = [ctx.source_file, loc && `(${loc})`, ctx.chunk_index != null && `#${ctx.chunk_index}`]
    .filter(Boolean)
    .join(" ");

  return (
    <li className="rounded border border-ink/12 bg-bg">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 px-2.5 py-2 text-left text-xs text-ink/80 transition hover:bg-ink/5"
      >
        {open ? <ChevronDown size={14} className="mt-0.5 shrink-0" /> : <ChevronRight size={14} className="mt-0.5 shrink-0" />}
        <span className="min-w-0 flex-1 break-words">{title || "Фрагмент"}</span>
      </button>
      {open && ctx.text && (
        <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap border-t border-ink/10 px-2.5 py-2 font-sans text-[11px] leading-relaxed text-ink/75">
          {ctx.text}
        </pre>
      )}
    </li>
  );
}

export default function SourceContextBlock({ contexts, title = "Фрагменты источника", compact = false }) {
  if (!contexts?.length) return null;

  return (
    <div className={compact ? "mt-2" : "flex flex-col gap-2"}>
      {title ? (
        <div className="text-[10px] uppercase tracking-wide text-ink/45">{title}</div>
      ) : null}
      <ul className={`flex flex-col gap-1.5 ${compact ? "" : ""}`}>
        {contexts.map((ctx, i) => (
          <ContextItem
            key={`${ctx.source_file}-${ctx.chunk_index}-${i}`}
            ctx={ctx}
            defaultOpen={!compact && i === 0}
          />
        ))}
      </ul>
    </div>
  );
}

export function RelationContextList({ items }) {
  if (!items?.length) return null;

  return (
    <div className="mt-2 flex flex-col gap-2">
      <div className="text-[10px] uppercase tracking-wide text-ink/45">Контекст связей</div>
      <ul className="flex flex-col gap-2">
        {items.map((item, i) => (
          <li key={`${item.relation_type}-${item.target_name}-${i}`} className="rounded border border-ink/10 bg-surface/50 p-2">
            <div className="text-[11px] font-medium text-ink/70">
              {item.relation_type}: {item.target_name}
            </div>
            <SourceContextBlock contexts={item.source_contexts} title="" compact />
          </li>
        ))}
      </ul>
    </div>
  );
}
