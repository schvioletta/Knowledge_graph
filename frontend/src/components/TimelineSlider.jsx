import { useEffect, useRef, useState } from "react";

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
    <div className="timeline">
      <label className="switch-label">
        <input type="checkbox" checked={enabled} onChange={(e) => onToggle(e.target.checked)} />
        История во времени
      </label>
      {enabled && (
        <div className="timeline-controls">
          <button onClick={() => setPlaying((p) => !p)}>{playing ? "⏸" : "▶"}</button>
          <input
            type="range"
            min={0}
            max={dates.length - 1}
            value={cursor}
            onChange={(e) => onCursorChange(Number(e.target.value))}
          />
          <span className="timeline-date">{currentDate}</span>
        </div>
      )}
    </div>
  );
}
