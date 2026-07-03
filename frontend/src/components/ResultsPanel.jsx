import { MessageSquare, Network, FileSearch, Loader2, FileText, Link as LinkIcon } from "lucide-react";
import DetailPanel from "./DetailPanel";

const TABS = [
  { id: "answer", label: "Текстовый ответ", icon: MessageSquare },
  { id: "documents", label: "По документам", icon: FileSearch },
  { id: "schema", label: "Схема графа", icon: Network },
];

const CONFIDENCE_STYLE = {
  "высокая": "border-secondary/40 text-secondary",
  "средняя": "border-accent/40 text-accent",
  "низкая": "border-ink/30 text-ink/60",
  "нет данных": "border-ink/20 text-ink/40",
};

function RagAnswer({ loading, result }) {
  if (loading) {
    return (
      <div className="flex h-full items-center gap-2 p-5 text-sm text-ink/50">
        <Loader2 size={14} className="animate-spin" />
        Ищу подтверждение в загруженных документах…
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex h-full items-center p-5 text-sm text-ink/50">
        Задайте вопрос — если он совпадёт с загруженными документами или ссылками,
        здесь появится ответ с точными цитатами источников.
      </div>
    );
  }

  const badgeClass = CONFIDENCE_STYLE[result.confidence] || CONFIDENCE_STYLE["нет данных"];

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-primary">
          Ответ по загруженным документам
        </span>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${badgeClass}`}>
          достоверность: {result.confidence}
        </span>
      </div>

      <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-ink">
        {result.answer}
      </pre>

      {result.citations.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="text-[11px] uppercase tracking-wide text-ink/50">Источники</div>
          <ul className="flex flex-col gap-1.5">
            {result.citations.map((c) => (
              <li key={c.index} className="rounded border border-ink/15 bg-surface px-2.5 py-1.5 text-xs">
                <div className="flex items-center gap-1.5 text-ink/80">
                  <span className="font-semibold text-primary">[{c.index}]</span>
                  {c.source_type === "link" ? <LinkIcon size={11} /> : <FileText size={11} />}
                  <span className="truncate">{c.title}</span>
                  <span className="ml-auto shrink-0 text-ink/40">{c.location}</span>
                </div>
                <p className="mt-1 line-clamp-2 text-ink/50">{c.snippet}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function ResultsPanel({
  activeTab,
  onTabChange,
  answer,
  onResetHighlight,
  ragResult,
  ragLoading,
  node,
  detail,
  onExpand,
  onClose,
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 border-b border-ink/10">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={`flex flex-1 items-center justify-center gap-1.5 border-b-2 px-2 py-2.5 text-[11px] font-semibold uppercase tracking-wide transition ${
                active
                  ? "border-primary text-primary"
                  : "border-transparent text-ink/50 hover:text-ink/80"
              }`}
            >
              <Icon size={13} />
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {activeTab === "answer" && (
          answer ? (
            <div className="flex flex-col gap-2 p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-primary">
                Ответ по графу
              </div>
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-ink">
                {answer}
              </pre>
              <button
                type="button"
                onClick={onResetHighlight}
                className="mt-1 self-start rounded border border-ink/20 px-2.5 py-1 text-xs text-ink/60 transition hover:text-ink"
              >
                Сбросить подсветку
              </button>
            </div>
          ) : (
            <div className="flex h-full items-center p-5 text-sm text-ink/50">
              Задайте вопрос в строке поиска — ответ появится здесь.
            </div>
          )
        )}

        {activeTab === "documents" && <RagAnswer loading={ragLoading} result={ragResult} />}

        {activeTab === "schema" && (
          <DetailPanel node={node} detail={detail} onExpand={onExpand} onClose={onClose} />
        )}
      </div>
    </div>
  );
}
