import { SlidersHorizontal } from "lucide-react";
import { TYPE_COLOR, TYPE_LABEL, FILTERABLE_TYPES, PALETTE } from "../constants";
import GapToggle from "./GapToggle";
import TimelineSlider from "./TimelineSlider";

export default function FilterDock({ typeFilter, onToggleType, onResetTypes, gapProps, timelineProps }) {
  const allActive = typeFilter.size === FILTERABLE_TYPES.length;

  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-4">
      <div className="flex items-center gap-2 text-ink/80">
        <SlidersHorizontal size={15} />
        <span className="text-xs font-semibold uppercase tracking-[0.15em]">Фильтры графа</span>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wide text-ink/50">Типы сущностей</span>
          {!allActive && (
            <button
              onClick={onResetTypes}
              className="text-[11px] text-primary transition hover:text-accent"
            >
              сбросить
            </button>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          {FILTERABLE_TYPES.map((type) => {
            const active = typeFilter.has(type);
            return (
              <label
                key={type}
                className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm transition hover:bg-ink/5"
              >
                <input
                  type="checkbox"
                  checked={active}
                  onChange={() => onToggleType(type)}
                  className="h-3.5 w-3.5 accent-primary"
                />
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ background: TYPE_COLOR[type], opacity: active ? 1 : 0.35 }}
                />
                <span className={active ? "text-ink" : "text-ink/40"}>
                  {TYPE_LABEL[type]}
                </span>
              </label>
            );
          })}
        </div>
      </div>

      <div className="h-px w-full bg-ink/10" />

      <GapToggle {...gapProps} />

      <div className="h-px w-full bg-ink/10" />

      <TimelineSlider {...timelineProps} />

      <div className="h-px w-full bg-ink/10" />

      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] uppercase tracking-wide text-ink/50">Стили связей</span>
        <div className="flex items-center gap-2 text-xs text-ink/60">
          <span className="inline-block h-0 w-4 border-b-2 border-dashed border-ink" />
          противоречие (CONTRADICTS)
        </div>
        <div className="flex items-center gap-2 text-xs text-ink/60">
          <span className="inline-block h-0 w-4 border-b-2 border-dotted border-ink" />
          требует проверки (NEEDS_REVIEW)
        </div>
      </div>

      <div className="h-px w-full bg-ink/10" />

      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] uppercase tracking-wide text-ink/50">Внешние источники</span>
        <div className="flex items-center gap-2 text-xs text-ink/60">
          <span
            className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-surface"
            style={{ background: PALETTE.secondary }}
          >
            S
          </span>
          Google Scholar (научная публикация)
        </div>
        <div className="flex items-center gap-2 text-xs text-ink/60">
          <span
            className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-surface"
            style={{ background: PALETTE.accent }}
          >
            P
          </span>
          Google Patents (патент)
        </div>
      </div>
    </div>
  );
}
