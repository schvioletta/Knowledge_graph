import { useEffect, useRef, useState } from "react";
import {
  Network, FileSearch, Loader2, FileText, Link as LinkIcon, AlertTriangle,
  Download, ChevronDown, FileJson, FileType,
} from "lucide-react";
import DetailPanel from "./DetailPanel";
import { exportAsJson, exportAsMarkdown, exportAsPdf } from "../utils/exportAnswer";

const TABS = [
  { id: "documents", label: "По документам", icon: FileSearch },
  { id: "schema", label: "Схема графа", icon: Network },
];

const CONFIDENCE_STYLE = {
  "высокая": "border-secondary/40 text-secondary",
  "средняя": "border-accent/40 text-accent",
  "низкая": "border-ink/30 text-ink/60",
  "нет данных": "border-ink/20 text-ink/40",
};

const EXPORT_FORMATS = [
  { id: "json", label: "JSON", icon: FileJson, run: exportAsJson },
  { id: "pdf", label: "PDF", icon: FileType, run: exportAsPdf },
  { id: "md", label: "Markdown (.md)", icon: FileText, run: exportAsMarkdown },
];

function ExportMenu({ question, result }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef(null);

  useEffect(() => {
    const onClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const handleExport = async (format) => {
    setOpen(false);
    setError("");
    setBusy(true);
    try {
      await format.run({ question, result });
    } catch (e) {
      setError(e.message || "Не удалось экспортировать");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div ref={ref} className="relative ml-auto">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={busy}
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded border border-ink/20 px-2.5 py-1 text-xs text-ink/70 transition hover:border-primary/50 hover:text-ink disabled:opacity-50"
      >
        {busy ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
        Выгрузить в
        <ChevronDown size={12} className={`transition ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-20 mt-1 w-48 overflow-hidden rounded-md border border-ink/15 bg-surface-deep shadow-lg">
          {EXPORT_FORMATS.map((f) => {
            const Icon = f.icon;
            return (
              <button
                key={f.id}
                type="button"
                onClick={() => handleExport(f)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-ink/80 transition hover:bg-ink/10 hover:text-ink"
              >
                <Icon size={13} />
                {f.label}
              </button>
            );
          })}
        </div>
      )}

      {error && <p className="absolute right-0 top-full mt-9 w-56 text-[11px] text-red-400">{error}</p>}
    </div>
  );
}

function QueryExpansions({ original, expansions }) {
  if (!expansions?.length) return null;
  return (
    <div className="rounded-md border border-primary/25 bg-primary/5 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-primary/80">
        Поиск по расширенным формулировкам
      </div>
      <p className="mt-1.5 text-xs text-ink/70">
        <span className="text-ink/50">Исходный вопрос: </span>
        {original}
      </p>
      <ul className="mt-2 flex flex-col gap-1.5">
        {expansions.map((q) => (
          <li
            key={q}
            className="rounded border border-accent/30 bg-accent/10 px-2 py-1 text-xs leading-snug text-ink"
          >
            {q}
          </li>
        ))}
      </ul>
    </div>
  );
}

function RagAnswer({ loading, result, question }) {
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
        {result.grounded && !result.llm_used && (
          <span
            className="flex items-center gap-1 rounded-full border border-orange-400/40 px-2 py-0.5 text-[10px] uppercase tracking-wide text-orange-300"
            title="LLM не ответил — ниже показаны найденные фрагменты источников без синтеза в связный текст"
          >
            <AlertTriangle size={10} />
            без LLM-синтеза
          </span>
        )}
        {result.grounded && <ExportMenu question={question} result={result} />}
      </div>

      <QueryExpansions
        original={result.query_original || question}
        expansions={result.query_expansions}
      />

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
  activeTab, onTabChange, question, ragResult, ragLoading, node, detail, onExpand, onClose,
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
        {activeTab === "documents" && <RagAnswer loading={ragLoading} result={ragResult} question={question} />}

        {activeTab === "schema" && (
          <DetailPanel node={node} detail={detail} onExpand={onExpand} onClose={onClose} />
        )}
      </div>
    </div>
  );
}
