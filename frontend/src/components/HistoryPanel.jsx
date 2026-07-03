import { Clock, Trash2, X } from "lucide-react";

const CONFIDENCE_DOT = {
  "высокая": "bg-secondary",
  "средняя": "bg-accent",
  "низкая": "bg-ink/40",
  "нет данных": "bg-ink/20",
};

function formatTime(ts) {
  const d = new Date(ts);
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay
    ? d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}

export default function HistoryPanel({ history, activeId, onSelect, onDelete, onClear }) {
  return (
    <div className="flex h-full flex-col gap-2 overflow-y-auto p-3">
      {history.length > 0 && (
        <button
          type="button"
          onClick={onClear}
          className="flex items-center gap-1.5 self-start rounded px-1.5 py-1 text-[11px] text-ink/50 transition hover:bg-red-400/10 hover:text-red-400"
        >
          <Trash2 size={11} />
          Очистить всё
        </button>
      )}

      {history.length === 0 ? (
        <div className="flex flex-1 items-center p-2 text-xs text-ink/40">
          Здесь появятся заданные вопросы — можно будет открыть любой ответ повторно, без нового запроса.
        </div>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {history.map((h) => {
            const active = h.id === activeId;
            return (
              <li key={h.id}>
                <div
                  className={`group flex items-start gap-1.5 rounded-md border px-2 py-1.5 transition ${
                    active
                      ? "border-primary/50 bg-primary/10"
                      : "border-ink/10 bg-surface hover:border-ink/25"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(h)}
                    className="flex min-w-0 flex-1 flex-col items-start gap-1 text-left"
                  >
                    <p className={`line-clamp-2 text-xs ${active ? "text-ink" : "text-ink/75"}`}>
                      {h.question}
                    </p>
                    <span className="flex items-center gap-1.5 text-[10px] text-ink/40">
                      <Clock size={9} />
                      {formatTime(h.timestamp)}
                      {h.ragResult?.confidence && (
                        <span className="flex items-center gap-1">
                          <span className={`h-1.5 w-1.5 rounded-full ${CONFIDENCE_DOT[h.ragResult.confidence] || "bg-ink/20"}`} />
                          {h.ragResult.confidence}
                        </span>
                      )}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(h.id)}
                    aria-label="Удалить из истории"
                    className="shrink-0 rounded p-0.5 text-ink/30 opacity-0 transition hover:bg-red-400/10 hover:text-red-400 group-hover:opacity-100"
                  >
                    <X size={12} />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
