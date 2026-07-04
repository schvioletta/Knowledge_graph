import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Circle,
  Download,
  ExternalLink,
  Loader2,
  Save,
} from "lucide-react";

const BASE = import.meta.env.VITE_API_BASE ?? "";

const RATING_LABELS = {
  1: "неверно",
  2: "частично",
  3: "с пробелами",
  4: "верно",
  5: "эталон",
};

function readEvalParams() {
  const p = new URLSearchParams(window.location.search);
  const version = p.get("v") === "2" ? "2" : "1";
  const source = p.get("source") === "auto" ? "auto" : "saved";
  return { version, source };
}

function setEvalParams(version, source) {
  const url = new URL(window.location.href);
  if (version === "2") url.searchParams.set("v", "2");
  else url.searchParams.delete("v");
  if (source === "auto") url.searchParams.set("source", "auto");
  else url.searchParams.delete("source");
  window.history.replaceState({}, "", url);
}

function isItemDone(item) {
  return item.rating != null && String(item.gold_answer || "").trim().length > 0;
}

function TriToggle({ label, value, onChange }) {
  const opts = [
    { v: null, label: "—" },
    { v: true, label: "да" },
    { v: false, label: "нет" },
  ];
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-ink/60">{label}</div>
      <div className="flex gap-1">
        {opts.map(({ v, label: l }) => (
          <button
            key={l}
            type="button"
            onClick={() => onChange(v)}
            className={`rounded px-2.5 py-1 text-xs transition ${
              value === v
                ? "bg-primary/25 text-primary ring-1 ring-primary/50"
                : "bg-white/5 text-ink/70 hover:bg-white/10"
            }`}
          >
            {l}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function RagEvalApp() {
  const [data, setData] = useState(null);
  const [idx, setIdx] = useState(0);
  const [version, setVersion] = useState(() => readEvalParams().version);
  const [source, setSource] = useState(() => readEvalParams().source);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saveMsg, setSaveMsg] = useState("");
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async (v, s) => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${BASE}/api/rag/eval?version=${v}&source=${s}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
      setIdx(0);
      setDirty(false);
    } catch (e) {
      setError(e.message || "Не удалось загрузить eval-набор");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(version, source);
  }, [load, version, source]);

  const switchVersion = (v) => {
    if (dirty && !window.confirm("Есть несохранённые изменения. Переключить набор?")) return;
    setVersion(v);
    setEvalParams(v, source);
  };

  const switchSource = (s) => {
    if (dirty && !window.confirm("Есть несохранённые изменения. Переключить источник?")) return;
    setSource(s);
    setEvalParams(version, s);
  };

  const items = data?.items ?? [];
  const item = items[idx];
  const doneCount = useMemo(() => items.filter(isItemDone).length, [items]);

  const patchItem = (patch) => {
    setData((prev) => {
      if (!prev) return prev;
      const next = { ...prev, items: [...prev.items] };
      next.items[idx] = { ...next.items[idx], ...patch };
      return next;
    });
    setDirty(true);
    setSaveMsg("");
  };

  const save = async () => {
    if (!data) return;
    setSaving(true);
    setSaveMsg("");
    setError("");
    try {
      const res = await fetch(`${BASE}/api/rag/eval?version=${version}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await res.json();
      setDirty(false);
      setSaveMsg(`Сохранено: data/rag_eval/${version === "2" ? "annotations_v2.json" : "annotations.json"}`);
    } catch (e) {
      setError(e.message || "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  const downloadJson = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = version === "2" ? "rag_eval_v2_annotations.json" : "rag_eval_annotations.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-ink/70">
        <Loader2 className="mr-2 animate-spin" size={20} />
        Загрузка…
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="mx-auto max-w-lg p-8 text-center">
        <p className="text-red-300">{error}</p>
        <button type="button" onClick={() => load(version, source)} className="mt-4 rounded bg-primary/20 px-4 py-2 text-sm text-primary">
          Повторить
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen text-ink">
      <header className="sticky top-0 z-10 border-b border-white/10 bg-bg/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <h1 className="text-lg font-semibold text-white">RAG Eval — разметка ответов</h1>
            <p className="text-xs text-ink/60">
              v{version} · {source === "auto" ? "авто-оценка" : "разметка"} · {doneCount}/{items.length} ·{" "}
              {data?.meta?.loaded_file ?? "—"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-white/10 p-0.5 text-xs">
              {["1", "2"].map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => switchVersion(v)}
                  className={`rounded-md px-2.5 py-1 transition ${
                    version === v ? "bg-primary text-bg" : "text-ink/70 hover:bg-white/5"
                  }`}
                >
                  v{v}
                </button>
              ))}
            </div>
            <div className="flex rounded-lg border border-white/10 p-0.5 text-xs">
              {[
                { id: "saved", label: "Ответы" },
                { id: "auto", label: "Авто-оценка" },
              ].map(({ id, label }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => switchSource(id)}
                  className={`rounded-md px-2.5 py-1 transition ${
                    source === id ? "bg-secondary/30 text-secondary" : "text-ink/70 hover:bg-white/5"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <a
              href="/"
              className="flex items-center gap-1 rounded px-3 py-1.5 text-xs text-ink/70 hover:bg-white/5"
            >
              <ExternalLink size={14} />
              Основной UI
            </a>
            <button
              type="button"
              onClick={downloadJson}
              className="flex items-center gap-1 rounded bg-white/5 px-3 py-1.5 text-xs hover:bg-white/10"
            >
              <Download size={14} />
              Скачать JSON
            </button>
            <button
              type="button"
              onClick={save}
              disabled={saving || !dirty || source === "auto" || data?.meta?.read_only}
              className="flex items-center gap-1 rounded bg-primary px-3 py-1.5 text-xs font-medium text-bg disabled:opacity-40"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              Сохранить
            </button>
          </div>
        </div>
        {(error || saveMsg) && (
          <div className={`px-4 pb-2 text-xs ${error ? "text-red-300" : "text-secondary"}`}>
            {error || saveMsg}
          </div>
        )}
      </header>

      <div className="mx-auto grid max-w-7xl gap-4 p-4 lg:grid-cols-[240px_1fr]">
        <aside className="space-y-1 rounded-xl border border-white/10 bg-black/20 p-2 lg:sticky lg:top-20 lg:self-start">
          {items.map((q, i) => {
            const done = isItemDone(q);
            return (
              <button
                key={q.id}
                type="button"
                onClick={() => setIdx(i)}
                className={`flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left text-sm transition ${
                  i === idx ? "bg-primary/15 text-white" : "hover:bg-white/5 text-ink/80"
                }`}
              >
                {done ? (
                  <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-secondary" />
                ) : (
                  <Circle size={16} className="mt-0.5 shrink-0 text-ink/30" />
                )}
                <span>
                  <span className="font-mono text-xs text-primary">{q.id}</span>
                  <span className="mt-0.5 block line-clamp-2 text-xs">{q.question}</span>
                </span>
              </button>
            );
          })}
        </aside>

        {item && (
          <main className="space-y-4">
            <div className="flex items-center justify-between gap-2">
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={idx === 0}
                  onClick={() => setIdx((i) => i - 1)}
                  className="rounded bg-white/5 p-2 disabled:opacity-30"
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  type="button"
                  disabled={idx >= items.length - 1}
                  onClick={() => setIdx((i) => i + 1)}
                  className="rounded bg-white/5 p-2 disabled:opacity-30"
                >
                  <ChevronRight size={18} />
                </button>
              </div>
              <span className="font-mono text-sm text-primary">{item.id}</span>
            </div>

            <section className="rounded-xl border border-white/10 bg-black/20 p-4">
              <div className="mb-2 flex flex-wrap gap-2 text-xs">
                <span className="rounded bg-white/10 px-2 py-0.5">{item.topic}</span>
                <span className="rounded bg-accent/20 px-2 py-0.5 text-accent">
                  ожид.: {item.expected_source}
                </span>
                <span className="rounded bg-white/10 px-2 py-0.5">
                  confidence: {item.confidence}
                </span>
                {item.v1_analog && (
                  <span className="rounded bg-white/10 px-2 py-0.5">аналог: {item.v1_analog}</span>
                )}
              </div>
              <h2 className="text-base font-medium text-white">{item.question}</h2>
            </section>

            <section className="rounded-xl border border-white/10 bg-black/20 p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink/50">
                Ответ системы
              </h3>
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{item.system_answer}</p>
            </section>

            {item.citations?.length > 0 && (
              <section className="rounded-xl border border-white/10 bg-black/20 p-4">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink/50">
                  Цитаты ({item.citations.length})
                </h3>
                <ul className="space-y-2">
                  {item.citations.map((c) => (
                    <li key={c.index} className="rounded-lg bg-white/5 p-3 text-xs">
                      <div className="mb-1 font-medium text-primary">
                        [{c.index}] {c.source_name} · score {c.score} · {c.location}
                      </div>
                      <p className="text-ink/70">{c.snippet}</p>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="rounded-xl border border-primary/30 bg-primary/5 p-4">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-primary">
                Ваша разметка
              </h3>

              <label className="mb-4 block">
                <span className="mb-1 block text-xs text-ink/60">Эталонный ответ (gold_answer)</span>
                <textarea
                  value={item.gold_answer || ""}
                  onChange={(e) => patchItem({ gold_answer: e.target.value })}
                  rows={4}
                  className="w-full rounded-lg border border-white/10 bg-bg/80 px-3 py-2 text-sm text-ink outline-none focus:border-primary/50"
                  placeholder="Краткий правильный ответ по документу…"
                />
              </label>

              <div className="mb-4">
                <span className="mb-2 block text-xs text-ink/60">Оценка (1–5)</span>
                <div className="flex flex-wrap gap-2">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => patchItem({ rating: n })}
                      className={`rounded-lg px-3 py-2 text-sm transition ${
                        item.rating === n
                          ? "bg-primary text-bg font-semibold"
                          : "bg-white/5 text-ink/80 hover:bg-white/10"
                      }`}
                    >
                      {n}
                      <span className="ml-1 hidden text-xs opacity-70 sm:inline">
                        {RATING_LABELS[n]}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="mb-4 grid gap-3 sm:grid-cols-3">
                <TriToggle
                  label="Retrieval OK — нашлись нужные документы?"
                  value={item.retrieval_ok ?? null}
                  onChange={(v) => patchItem({ retrieval_ok: v })}
                />
                <TriToggle
                  label="Factual OK — факты верны?"
                  value={item.factual_ok ?? null}
                  onChange={(v) => patchItem({ factual_ok: v })}
                />
                <TriToggle
                  label="Citation OK — ссылки [N] корректны?"
                  value={item.citation_ok ?? null}
                  onChange={(v) => patchItem({ citation_ok: v })}
                />
              </div>

              <label className="block">
                <span className="mb-1 block text-xs text-ink/60">Заметки</span>
                <textarea
                  value={item.notes || ""}
                  onChange={(e) => patchItem({ notes: e.target.value })}
                  rows={2}
                  className="w-full rounded-lg border border-white/10 bg-bg/80 px-3 py-2 text-sm text-ink outline-none focus:border-primary/50"
                  placeholder="Ошибки, пропуски, комментарии…"
                />
              </label>
            </section>
          </main>
        )}
      </div>
    </div>
  );
}
