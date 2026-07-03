import { MessageSquare, Network } from "lucide-react";
import DetailPanel from "./DetailPanel";

const TABS = [
  { id: "answer", label: "Текстовый ответ", icon: MessageSquare },
  { id: "schema", label: "Схема графа", icon: Network },
];

export default function ResultsPanel({
  activeTab,
  onTabChange,
  answer,
  onResetHighlight,
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
        {activeTab === "answer" ? (
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
        ) : (
          <DetailPanel node={node} detail={detail} onExpand={onExpand} onClose={onClose} />
        )}
      </div>
    </div>
  );
}
