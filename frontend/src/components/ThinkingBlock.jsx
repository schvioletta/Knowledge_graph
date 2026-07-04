import { useEffect, useRef, useState } from "react";
import { Brain, ChevronDown, Loader2 } from "lucide-react";

const STAGE_LABEL = {
  expand: "Расширение запроса",
  discover: "Подбор документов",
  retrieve: "Отбор фрагментов",
  entities: "Извлечение сущностей",
  synthesize: "Синтез ответа",
};

// Блок «ход рассуждений»: во время генерации раскрыт и обновляется потоково
// (курсивом), после завершения автоматически сворачивается в компактный заголовок.
// Раскрытие/сворачивание не влияет на layout страницы — родительская панель имеет
// фиксированную высоту и внутренний скролл, блок лишь меняет свою высоту внутри неё.
export default function ThinkingBlock({ steps, streaming }) {
  const [open, setOpen] = useState(true);
  const wasStreaming = useRef(false);
  const scrollRef = useRef(null);

  // Старт нового потока — раскрываем; завершение (streaming true -> false) —
  // автоматически сворачиваем в компактный вид.
  useEffect(() => {
    if (streaming && !wasStreaming.current) setOpen(true);
    if (!streaming && wasStreaming.current) setOpen(false);
    wasStreaming.current = streaming;
  }, [streaming]);

  // Автопрокрутка к последней строке рассуждений во время стрима.
  useEffect(() => {
    if (open && streaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [steps, open, streaming]);

  if (!steps?.length && !streaming) return null;

  return (
    <div className="rounded-md border border-primary/20 bg-primary/[0.04]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        {streaming ? (
          <Loader2 size={13} className="shrink-0 animate-spin text-primary" />
        ) : (
          <Brain size={13} className="shrink-0 text-primary/70" />
        )}
        <span className="text-[11px] font-semibold uppercase tracking-wide text-primary/80">
          {streaming
            ? "Ход рассуждений…"
            : open
              ? "Ход рассуждений"
              : "Показать ход рассуждений"}
        </span>
        <span className="ml-auto text-[10px] text-ink/40">{steps?.length || 0} шаг(ов)</span>
        <ChevronDown
          size={13}
          className={`shrink-0 text-ink/40 transition ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          ref={scrollRef}
          className="max-h-40 overflow-y-auto border-t border-primary/10 px-3 py-2"
        >
          <ul className="flex flex-col gap-1.5">
            {steps.map((s, i) => (
              <li key={i} className="flex gap-2 text-xs italic leading-relaxed text-ink/60">
                <span className="mt-[3px] h-1 w-1 shrink-0 rounded-full bg-primary/50" />
                <span>
                  {STAGE_LABEL[s.stage] && (
                    <span className="mr-1 not-italic font-medium text-primary/60">
                      {STAGE_LABEL[s.stage]}:
                    </span>
                  )}
                  {s.text}
                </span>
              </li>
            ))}
            {streaming && (
              <li className="flex gap-2 pl-3 text-xs italic text-ink/40">
                <Loader2 size={11} className="mt-0.5 animate-spin" />
                анализирую…
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
