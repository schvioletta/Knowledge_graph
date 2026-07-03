import { useEffect, useRef, useState } from "react";
import { Play, Pause } from "lucide-react";

export default function TimelineSlider({ enabled, onToggle, dates, cursor, onCursorChange }) {
  const [playing, setPlaying] = useState(false);
  const intervalRef = useRef();

  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(() => {
        onCursorChange((c) => {
          const next = c + 1;
          if (next >= dates.length) {
            setPlaying(false);
            return c;
          }
          return next;
        });
      }, 700);
    }
    return () => clearInterval(intervalRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, dates.length]);

  if (!dates || dates.length === 0) return null;
  const currentDate = dates[Math.min(cursor, dates.length - 1)]?.date;

  return (
    <div className="flex flex-col gap-2">
      <label className="flex cursor-pointer items-center gap-2 text-sm text-ink/80">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="h-3.5 w-3.5 accent-secondary"
        />
        История во времени
      </label>
      {enabled && (
        <div className="flex items-center gap-2 text-xs">
          <button
            onClick={() => setPlaying((p) => !p)}
            className="flex h-6 w-6 items-center justify-center rounded border border-ink/20 text-ink/70 transition hover:border-secondary/50 hover:text-ink"
          >
            {playing ? <Pause size={11} /> : <Play size={11} />}
          </button>
          <input
            type="range"
            min={0}
            max={dates.length - 1}
            value={cursor}
            onChange={(e) => onCursorChange(Number(e.target.value))}
            className="h-1 flex-1 accent-secondary"
          />
          <span className="tabular-nums text-ink/50">{currentDate}</span>
        </div>
      )}
    </div>
  );
}
