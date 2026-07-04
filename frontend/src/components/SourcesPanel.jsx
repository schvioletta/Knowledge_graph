import { useRef, useState } from "react";
import { Upload, Link as LinkIcon, FileText, Loader2, AlertCircle, CheckCircle2, Info, X } from "lucide-react";

const ACCEPTED = ".pdf,.docx,.txt";

export default function SourcesPanel({
  documents,
  onUpload,
  onAddLink,
  onDelete,
  deletingId,
  uploading,
  linkSubmitting,
  error,
  notice,
}) {
  const fileInputRef = useRef();
  const [linkValue, setLinkValue] = useState("");

  const submitLink = (e) => {
    e.preventDefault();
    const url = linkValue.trim();
    if (!url) return;
    onAddLink(url);
    setLinkValue("");
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) onUpload(file);
    e.target.value = "";
  };

  return (
    <div className="flex flex-col gap-2 rounded-md border border-ink/15 bg-surface-deep p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-ink/50">
          База знаний для чата
        </span>
        <span className="text-[11px] text-ink/40">
          {documents.length > 0
            ? `${documents.length} источник(ов)`
            : "пока пусто — при запросе подберутся из корпуса"}
        </span>

        <div className="ml-auto flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED}
            className="hidden"
            onChange={handleFileChange}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-1.5 rounded border border-ink/20 px-2.5 py-1 text-xs text-ink/80 transition hover:border-primary/50 hover:text-ink disabled:opacity-50"
          >
            {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
            {uploading ? "Загрузка…" : "Загрузить файл"}
          </button>
        </div>
      </div>

      <form onSubmit={submitLink} className="flex items-center gap-2">
        <div className="flex flex-1 items-center gap-1.5 rounded border border-ink/20 bg-surface px-2 py-1">
          <LinkIcon size={13} className="shrink-0 text-ink/40" />
          <input
            value={linkValue}
            onChange={(e) => setLinkValue(e.target.value)}
            placeholder="Ссылка на статью или документ (https://…)"
            className="min-w-0 flex-1 bg-transparent text-xs text-ink placeholder:text-ink/40 outline-none focus:outline-none focus-visible:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={linkSubmitting || !linkValue.trim()}
          className="flex items-center gap-1.5 rounded border border-ink/20 px-2.5 py-1 text-xs text-ink/80 transition hover:border-primary/50 hover:text-ink disabled:opacity-50"
        >
          {linkSubmitting ? <Loader2 size={13} className="animate-spin" /> : null}
          Добавить
        </button>
      </form>

      {error && (
        <div className="flex items-center gap-1.5 text-xs text-red-400">
          <AlertCircle size={13} className="shrink-0" />
          {error}
        </div>
      )}

      {!error && notice && (
        <div className="flex items-center gap-1.5 text-xs text-ink/50">
          <Info size={13} className="shrink-0" />
          {notice}
        </div>
      )}

      {documents.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {documents.map((d) => (
            <li
              key={d.id}
              title={d.source_name}
              className="flex items-center gap-1.5 rounded-full border border-ink/15 bg-surface px-2 py-1 text-[11px] text-ink/70"
            >
              {d.source_type === "link" ? <LinkIcon size={11} /> : <FileText size={11} />}
              <span className="max-w-[180px] truncate">{d.title}</span>
              {d.attach_source === "auto" && (
                <span className="rounded bg-primary/15 px-1 text-[9px] font-semibold uppercase text-primary">
                  авто
                </span>
              )}
              {(d.year || d.domain) && (
                <span className="text-[9px] text-ink/40">
                  {[d.year, d.domain !== "unknown" ? d.domain : null].filter(Boolean).join(" · ")}
                </span>
              )}
              {d.status === "ready" ? (
                <span className="flex items-center gap-0.5 text-secondary">
                  <CheckCircle2 size={11} />
                  {d.num_chunks}
                </span>
              ) : (
                <span className="flex items-center gap-0.5 text-red-400" title={d.error || ""}>
                  <AlertCircle size={11} />
                  ошибка
                </span>
              )}
              <button
                type="button"
                onClick={() => onDelete(d.id)}
                disabled={deletingId === d.id}
                aria-label={`Удалить источник «${d.title}»`}
                className="ml-0.5 rounded-full p-0.5 text-ink/40 transition hover:bg-red-400/10 hover:text-red-400 disabled:opacity-50"
              >
                {deletingId === d.id ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
