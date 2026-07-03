import { AlertTriangle, ExternalLink, FileText, Loader2, Network } from "lucide-react";
import { api } from "../api";
import SourceContextBlock, { RelationContextList } from "./SourceContextBlock";

const CONFIDENCE_STYLE = {
  "высокая": "border-secondary/40 bg-secondary/5 text-secondary",
  "средняя": "border-accent/40 bg-accent/5 text-accent",
  "низкая": "border-ink/20 bg-ink/5 text-ink/60",
  "?": "border-ink/15 bg-ink/5 text-ink/50",
};

const ENTITY_LABELS = {
  material: "Материал",
  process: "Процесс",
  condition: "Условие",
  property: "Свойство",
  equipment: "Оборудование",
  facility: "Предприятие",
  country_filter: "Страна",
  year_cutoff: "С",
};

function Field({ label, value }) {
  if (!value || (Array.isArray(value) && value.length === 0)) return null;
  const text = Array.isArray(value) ? value.join(", ") : value;
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-wide text-ink/45">{label}</dt>
      <dd className="text-xs leading-snug text-ink">{text}</dd>
    </div>
  );
}

function publicationFileUrl(pub) {
  if (!pub.file_available) return null;
  if (pub.file_url) return api.sourceFileUrl(pub.file_url);
  if (pub.source_file?.trim()) return api.sourceFileUrl(pub.source_file.trim());
  return null;
}

function PublicationItem({ pub, onSelectPublication, compact = false }) {
  const fileUrl = publicationFileUrl(pub);
  const graphClickable = Boolean(pub.id && onSelectPublication);

  return (
    <li className={compact ? "" : "rounded-md border border-ink/12 bg-bg px-3 py-2"}>
      <div className="flex items-start gap-2">
        <FileText size={14} className="mt-0.5 shrink-0 text-ink/45" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium text-ink">{pub.name}</span>
          {pub.source_file && (
            <span className="mt-0.5 block truncate text-xs text-ink/50">{pub.source_file}</span>
          )}
          {pub.date && (
            <span className="mt-0.5 block text-[11px] text-ink/40">{pub.date}</span>
          )}
          <span className="mt-2 flex flex-wrap items-center gap-2">
            {fileUrl ? (
              <a
                href={fileUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded border border-primary/30 bg-primary/5 px-2 py-0.5 text-[11px] font-medium text-primary transition hover:bg-primary/10"
              >
                <ExternalLink size={11} />
                Открыть файл
              </a>
            ) : pub.source_file ? (
              <span className="text-[11px] text-ink/40">
                {pub.source_file} — не найден в data/raw
              </span>
            ) : null}
            {graphClickable && (
              <button
                type="button"
                onClick={() => onSelectPublication(pub.id)}
                className="inline-flex items-center gap-1 rounded border border-ink/20 px-2 py-0.5 text-[11px] text-ink/70 transition hover:border-ink/40 hover:text-ink"
              >
                <Network size={11} />
                На графе
              </button>
            )}
          </span>
        </span>
      </div>
    </li>
  );
}

function PublicationsBlock({ publications, onSelectPublication, title = "Документы-источники" }) {
  if (!publications?.length) return null;

  return (
    <div className="flex flex-col gap-2">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-ink/50">
        {title} ({publications.length})
      </div>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {publications.map((pub) => (
          <PublicationItem
            key={pub.id || pub.source_file || pub.name}
            pub={pub}
            onSelectPublication={onSelectPublication}
          />
        ))}
      </ul>
      <p className="text-[11px] text-ink/45">
        «Открыть файл» — PDF/PPTX из data/raw в новой вкладке; «На графе» — узел публикации в правой панели.
      </p>
    </div>
  );
}

function DetectedFilters({ entities, numericFilters }) {
  const chips = [];
  for (const [key, label] of Object.entries(ENTITY_LABELS)) {
    const val = entities?.[key];
    if (val && typeof val === "object" && val.name) {
      chips.push({ label, value: val.name });
    } else if (val && typeof val === "string") {
      chips.push({ label, value: val });
    }
  }
  if (numericFilters?.length) {
    chips.push({
      label: "Числовые ограничения",
      value: numericFilters.map(([k, op, v]) => `${k} ${op} ${v}`).join("; "),
    });
  }
  if (!chips.length) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {chips.map((chip) => (
        <span
          key={`${chip.label}-${chip.value}`}
          className="inline-flex max-w-full items-center gap-1 rounded-full border border-ink/15 bg-bg px-2 py-0.5 text-[11px] text-ink/70"
        >
          <span className="shrink-0 text-ink/45">{chip.label}:</span>
          <span className="truncate">{chip.value}</span>
        </span>
      ))}
    </div>
  );
}

function ExperimentCard({ exp, onSelectPublication }) {
  const badgeClass = CONFIDENCE_STYLE[exp.confidence] || CONFIDENCE_STYLE["?"];

  return (
    <article className={`rounded-md border bg-bg p-3 ${exp.approximate ? "border-accent/35" : "border-ink/12"}`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] text-ink/50">{exp.id}</span>
        {exp.approximate && (
          <span className="rounded border border-accent/40 bg-accent/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-accent">
            близкое совпадение
          </span>
        )}
        <span className="rounded border border-ink/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ink/55">
          {exp.country}
        </span>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${badgeClass}`}>
          {exp.confidence}
        </span>
      </div>
      <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Материал" value={exp.materials} />
        <Field label="Процесс" value={exp.processes} />
        <Field label="Условие" value={exp.conditions} />
        <Field label="Оборудование" value={exp.equipment} />
        <Field label="Предприятие" value={exp.facilities} />
        <Field label="Эффект" value={exp.effect} />
        <Field label="Вывод" value={exp.conclusions} />
        <Field label="Команда" value={exp.team} />
      </dl>
      {exp.publications?.length > 0 && (
        <div className="mt-3 border-t border-ink/10 pt-3">
          <div className="mb-1.5 text-[10px] uppercase tracking-wide text-ink/45">Документы</div>
          <ul className="flex flex-col gap-1.5">
            {exp.publications.map((pub) => (
              <PublicationItem
                key={pub.id || pub.source_file || pub.name}
                pub={pub}
                onSelectPublication={onSelectPublication}
                compact
              />
            ))}
          </ul>
        </div>
      )}
      {exp.source_contexts?.length > 0 && (
        <div className="mt-3 border-t border-ink/10 pt-3">
          <SourceContextBlock contexts={exp.source_contexts} />
        </div>
      )}
      {exp.relation_contexts?.length > 0 && (
        <RelationContextList items={exp.relation_contexts} />
      )}
    </article>
  );
}

export default function GraphAnswer({ result, loading, onResetHighlight, onSelectPublication }) {
  if (loading) {
    return (
      <div className="border-b border-ink/10 bg-surface/60 px-6 py-4">
        <div className="flex items-center gap-2 text-sm text-ink/50">
          <Loader2 size={14} className="animate-spin" />
          Ищу в графе знаний…
        </div>
      </div>
    );
  }

  if (!result) {
    return null;
  }

  const {
    answer,
    exact_match: exactMatch = true,
    experiments = [],
    publications = [],
    contradictions = [],
    gaps_mentioned = [],
    detected_entities = {},
  } = result;
  const numericFilters = detected_entities.numeric_filters;

  return (
    <div className="border-b border-ink/10 bg-surface/60 px-6 py-5">
      <div className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-primary">
            Ответ по графу
          </div>
          <button
            type="button"
            onClick={onResetHighlight}
            className="shrink-0 rounded border border-ink/20 px-2.5 py-1 text-xs text-ink/60 transition hover:text-ink"
          >
            Сбросить подсветку
          </button>
        </div>

        <DetectedFilters entities={detected_entities} numericFilters={numericFilters} />

        {!exactMatch && experiments.length > 0 && (
          <div className="rounded-md border border-accent/35 bg-accent/5 px-3 py-2 text-sm text-ink/85">
            Точного совпадения с запросом не найдено — ниже показаны ближайшие эксперименты из графа.
          </div>
        )}

        {answer && (
          <p className="max-w-4xl text-sm leading-relaxed text-ink">{answer}</p>
        )}

        <PublicationsBlock
          publications={publications}
          onSelectPublication={onSelectPublication}
        />

        {gaps_mentioned.length > 0 && !exactMatch && (
          <div className="rounded-md border border-ink/15 bg-bg px-3 py-2 text-sm text-ink/70">
            {gaps_mentioned.join("; ")}
          </div>
        )}

        {gaps_mentioned.length > 0 && !experiments.length && (
          <div className="rounded-md border border-accent/30 bg-accent/5 px-3 py-2 text-sm text-ink/80">
            Обнаружен пробел в данных: {gaps_mentioned.join("; ")}
          </div>
        )}

        {experiments.length > 0 && (
          <div className="flex flex-col gap-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-ink/50">
              {exactMatch ? "Эксперименты" : "Ближайшие эксперименты"} ({experiments.length})
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {experiments.map((exp) => (
                <ExperimentCard
                  key={exp.id}
                  exp={exp}
                  onSelectPublication={onSelectPublication}
                />
              ))}
            </div>
          </div>
        )}

        {contradictions.length > 0 && (
          <div className="rounded-md border border-accent/40 bg-accent/5 p-3">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-accent">
              <AlertTriangle size={13} />
              Противоречия в выводах
            </div>
            <ul className="flex flex-col gap-1.5 text-sm text-ink/80">
              {contradictions.map((c) => (
                <li key={`${c.a.id}-${c.b.id}`}>
                  «{c.a.name}» противоречит «{c.b.name}»
                  {c.note ? `. ${c.note}` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
