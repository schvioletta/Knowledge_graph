import { useEffect, useRef, useState } from "react";
import {
  Network, FileSearch, Loader2, FileText, Link as LinkIcon, AlertTriangle,
  Download, ChevronDown, FileJson, FileType,
  Database, GraduationCap, Award, ExternalLink, SearchX,
} from "lucide-react";
import DetailPanel from "./DetailPanel";
import ThinkingBlock from "./ThinkingBlock";
import AnswerContent from "./AnswerContent";
import HighlightedText from "./HighlightedText";
import { exportAsJson, exportAsMarkdown, exportAsPdf } from "../utils/exportAnswer";
import { cleanLocation, cleanSnippet } from "../utils/sourceFormat";

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

const EXPAND_LLM_LABELS = {
  ollama: "Qwen · локально",
  gigachat: "GigaChat · облако",
};

function QueryExpansions({ original, expansions, expandLlm }) {
  if (!expansions?.length) return null;
  const sourceLabel = EXPAND_LLM_LABELS[expandLlm];
  const sourceTitle =
    expandLlm === "ollama"
      ? "Перефразировки сгенерированы локально через Ollama (Qwen)"
      : expandLlm === "gigachat"
        ? "Перефразировки сгенерированы через GigaChat (облако, fallback)"
        : null;
  return (
    <div className="rounded-md border border-primary/25 bg-primary/5 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-primary/80">
          Поиск по расширенным формулировкам
        </div>
        {sourceLabel && (
          <span
            title={sourceTitle}
            className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${
              expandLlm === "ollama"
                ? "border-secondary/40 text-secondary"
                : "border-accent/40 text-accent"
            }`}
          >
            {sourceLabel}
          </span>
        )}
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

const STEP_TYPE_COLOR = {
  material: "text-primary",
  process: "text-secondary",
  equipment: "text-accent",
  result: "text-ink/90",
};

function formatStepItems(items) {
  if (!items?.length) return null;
  return items.map((i) => i.name).filter(Boolean).join(", ");
}

function ExperimentChains({ chains, onHighlightChain }) {
  if (!chains?.length) return null;

  return (
    <div className="rounded-md border border-secondary/25 bg-secondary/5 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-secondary/90">
        Цепочки: материал → процесс → оборудование → результат
      </div>
      <ul className="mt-2 flex flex-col gap-2">
        {chains.map((chain) => {
          const pub = chain.publication?.name;
          const title = chain.experiment_name || "Эксперимент";
          return (
            <li key={chain.experiment_id}>
              <button
                type="button"
                onClick={() => onHighlightChain?.(chain.node_ids || chain.path_ids)}
                className="w-full rounded border border-ink/10 bg-surface/80 px-2.5 py-2 text-left transition hover:border-primary/40 hover:bg-primary/5"
                title="Подсветить цепочку на графе"
              >
                <div className="text-[10px] text-ink/45">
                  {pub ? `${pub} · ` : ""}
                  {title}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-1 gap-y-0.5 text-xs leading-snug">
                  {chain.steps.map((step, idx) => {
                    const text = formatStepItems(step.items);
                    return (
                      <span key={step.key} className="inline-flex items-center gap-1">
                        {idx > 0 && <span className="text-ink/30">→</span>}
                        {text ? (
                          <span className={STEP_TYPE_COLOR[step.key] || "text-ink"}>{text}</span>
                        ) : (
                          <span className="text-ink/25">—</span>
                        )}
                      </span>
                    );
                  })}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function relevanceStyle(relevance) {
  if (relevance >= 0.66) return "border-secondary/40 text-secondary";
  if (relevance >= 0.4) return "border-accent/40 text-accent";
  return "border-ink/25 text-ink/50";
}

// Одна карточка внешнего источника (научная публикация или патент) со всеми
// обязательными полями: название+ссылка, авторы, год, журнал/номер патента,
// краткое описание, ключевые слова находки и оценка релевантности.
function ExternalSourceCard({ item, index, prefix }) {
  const authors = (item.authors || []).join(", ");
  const meta = [authors, item.year, item.venue].filter(Boolean).join(" · ");
  return (
    <li className="rounded border border-ink/15 bg-surface px-2.5 py-1.5 text-xs">
      <div className="flex items-start gap-1.5 text-ink/80">
        <span className="font-semibold text-primary">[{prefix}{index}]</span>
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="source-glow flex-1 font-medium leading-snug underline-offset-2 hover:underline"
            title={item.url}
          >
            {item.title || "(без названия)"}
            <ExternalLink size={10} className="ml-1 inline align-baseline text-ink/40" />
          </a>
        ) : (
          <span className="flex-1 font-medium leading-snug">{item.title || "(без названия)"}</span>
        )}
        {typeof item.relevance === "number" && (
          <span
            title="Оценка релевантности запросу (0–1)"
            className={`ml-auto shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] uppercase tracking-wide ${relevanceStyle(item.relevance)}`}
          >
            {item.relevance.toFixed(2)}
          </span>
        )}
      </div>
      {meta && <div className="mt-0.5 text-[11px] text-ink/45">{meta}</div>}
      {item.snippet && <p className="mt-1 line-clamp-2 text-ink/55">{item.snippet}</p>}
      {(item.matched_keywords || []).length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          <span className="text-[9px] uppercase tracking-wide text-ink/35">по словам:</span>
          {item.matched_keywords.map((k) => (
            <span key={k} className="rounded bg-primary/10 px-1 py-0.5 text-[9px] text-primary/80">
              {k}
            </span>
          ))}
        </div>
      )}
    </li>
  );
}

function SourceCategory({ icon: Icon, title, count, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-ink/50">
        <Icon size={12} className="text-ink/40" />
        {title}
        {count != null && <span className="text-ink/30">· {count}</span>}
      </div>
      {children}
    </div>
  );
}

// Раздел «Источники» с отдельными категориями: внутренняя база (RAG/документы),
// Google Scholar, Google Patents. Внешний блок полностью независим от внутреннего —
// если внешних не нашлось, показывается штатное сообщение, а цитаты RAG остаются.
function SourcesSection({ citations, external, highlightEntities }) {
  const scholar = external?.scholar || [];
  const patents = external?.patents || [];
  const externalEnabled = external?.enabled;
  const nothingExternal = externalEnabled && scholar.length === 0 && patents.length === 0;
  const notFoundMsg =
    external?.message || "По данным ключевым словам релевантные публикации и патенты не найдены";

  if (!citations.length && !externalEnabled) return null;

  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-ink/60">Источники</div>

      {citations.length > 0 && (
        <SourceCategory icon={Database} title="Внутренняя база знаний (RAG / документы)" count={citations.length}>
          <ul className="flex flex-col gap-1.5">
            {citations.map((c) => {
              const location = cleanLocation(c.location);
              const isLink = c.source_type === "link";
              return (
                <li key={c.index} className="rounded border border-ink/15 bg-surface px-2.5 py-1.5 text-xs">
                  <div className="flex items-center gap-1.5 text-ink/80">
                    <span className="font-semibold text-primary">[{c.index}]</span>
                    {isLink ? <LinkIcon size={11} /> : <FileText size={11} />}
                    {isLink && c.source_name ? (
                      <a
                        href={c.source_name}
                        target="_blank"
                        rel="noreferrer"
                        className="source-glow truncate underline-offset-2 hover:underline"
                        title={c.source_name}
                      >
                        {c.title}
                      </a>
                    ) : (
                      <span className="source-glow truncate" title={c.title}>{c.title}</span>
                    )}
                    {location && <span className="ml-auto shrink-0 text-ink/40">{location}</span>}
                  </div>
                  <p className="mt-1 line-clamp-2 text-ink/50">
                    <HighlightedText text={cleanSnippet(c.snippet)} entities={highlightEntities} />
                  </p>
                </li>
              );
            })}
          </ul>
        </SourceCategory>
      )}

      {externalEnabled && scholar.length > 0 && (
        <SourceCategory icon={GraduationCap} title="Google Scholar — научные публикации" count={scholar.length}>
          <ul className="flex flex-col gap-1.5">
            {scholar.map((s, i) => (
              <ExternalSourceCard key={`s${i}`} item={s} index={i + 1} prefix="S" />
            ))}
          </ul>
        </SourceCategory>
      )}

      {externalEnabled && patents.length > 0 && (
        <SourceCategory icon={Award} title="Google Patents — патенты" count={patents.length}>
          <ul className="flex flex-col gap-1.5">
            {patents.map((p, i) => (
              <ExternalSourceCard key={`p${i}`} item={p} index={i + 1} prefix="P" />
            ))}
          </ul>
        </SourceCategory>
      )}

      {nothingExternal && (
        <div className="flex items-center gap-1.5 rounded border border-ink/10 bg-surface/60 px-2.5 py-2 text-xs text-ink/50">
          <SearchX size={13} className="shrink-0 text-ink/40" />
          {notFoundMsg}
        </div>
      )}
    </div>
  );
}

function RagAnswer({
  result, question, streaming, thinkingSteps, streamAnswer, liveEntities, onEntityClick, onHighlightChain,
}) {
  const hasResult = !!result;

  // Пустое состояние — нет ни потока, ни результата, ни рассуждений.
  if (!streaming && !hasResult && !thinkingSteps?.length) {
    return (
      <div className="flex h-full items-center p-5 text-sm text-ink/50">
        Задайте вопрос — если он совпадёт с загруженными документами или ссылками,
        здесь появится ответ с точными цитатами источников.
      </div>
    );
  }

  const badgeClass = CONFIDENCE_STYLE[result?.confidence] || CONFIDENCE_STYLE["нет данных"];

  return (
    <div className="flex flex-col gap-3 p-4">
      {hasResult && (
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
      )}

      <ThinkingBlock steps={thinkingSteps} streaming={streaming} />

      {hasResult && (
        <>
          <QueryExpansions
            original={result.query_original || question}
            expansions={result.query_expansions}
            expandLlm={result.expand_llm}
          />
          <ExperimentChains chains={result.experiment_chains} onHighlightChain={onHighlightChain} />
          {result.chunk_graph_stats && (
            <p className="text-xs text-ink/50">
              Граф из фрагментов: {result.chunk_graph_stats.entities} сущностей,{" "}
              {result.chunk_graph_stats.relations} связей
              {result.chunk_graph_stats.chunks != null && ` · ${result.chunk_graph_stats.chunks} чанков`}
              {result.chunk_graph_stats.llm_skipped && " (NER без LLM — только публикации)"}
            </p>
          )}
        </>
      )}

      {/* Ответ: во время потока — накапливаемый текст с курсором; после — финальный
          с подсветкой ключевых сущностей. */}
      {hasResult ? (
        <AnswerContent
          text={result.answer}
          entities={result.highlight_entities}
          onEntityClick={onEntityClick}
        />
      ) : streamAnswer ? (
        <AnswerContent
          text={streamAnswer}
          entities={liveEntities}
          onEntityClick={onEntityClick}
          streaming
        />
      ) : streaming ? (
        <div className="flex items-center gap-2 text-sm text-ink/40">
          <Loader2 size={13} className="animate-spin" />
          Формирую ответ…
        </div>
      ) : null}

      {hasResult && (
        <SourcesSection
          citations={result.citations}
          external={result.external}
          highlightEntities={result.highlight_entities}
        />
      )}
    </div>
  );
}

export default function ResultsPanel({
  activeTab, onTabChange, question, ragResult, node, detail, onExpand, onClose,
  onHighlightChain, thinkingSteps, streamAnswer, streaming, liveEntities, onEntityClick,
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
        {activeTab === "documents" && (
          <RagAnswer
            result={ragResult}
            question={question}
            streaming={streaming}
            thinkingSteps={thinkingSteps}
            streamAnswer={streamAnswer}
            liveEntities={liveEntities}
            onEntityClick={onEntityClick}
            onHighlightChain={onHighlightChain}
          />
        )}

        {activeTab === "schema" && (
          <DetailPanel node={node} detail={detail} onExpand={onExpand} onClose={onClose} />
        )}
      </div>
    </div>
  );
}
