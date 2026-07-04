// Очистка технических маркеров разбиения документа из отображаемых источников.
// Индексатор помечает фрагменты внутренними метками ("para 12", "page 5",
// "slide 3", "table 2"), а текст чанка склеивается как "[para 12] ...". Для
// пользователя "para X" (номер абзаца) — шум; страница/слайд/таблица —
// осмысленная привязка. Показываем только осмысленное, внутренние метки убираем.

const LOC_LABELS = {
  page: "стр.",
  page_ru: "стр.",
  slide: "слайд",
  table: "таблица",
};

// Внутренние bracket-маркеры внутри текста сниппета: [para 12], [page 5] и т.п.
const INLINE_MARKER_RE = /\[\s*(?:para|paragraph|page|slide|table|стр\.?|страница|слайд|таблица)\s*\d+\s*\]/gi;

// Один токен локации: "page 5" / "para 12" / "slide 3".
const LOC_TOKEN_RE = /(para|paragraph|page|slide|table)\s*(\d+)/i;

/**
 * Человекочитаемая локация источника без внутренних меток абзацев.
 * "para 0, para 2" -> "" (только внутренние абзацы — показывать нечего)
 * "page 5, page 6" -> "стр. 5, 6"
 * "slide 3"        -> "слайд 3"
 * Возвращает "" если осмысленной привязки нет.
 */
export function cleanLocation(location) {
  if (!location) return "";
  const byKind = {};
  for (const raw of String(location).split(",")) {
    const m = raw.trim().match(LOC_TOKEN_RE);
    if (!m) continue;
    const kind = m[1].toLowerCase();
    if (kind === "para" || kind === "paragraph") continue; // внутренняя метка — скрываем
    (byKind[kind] ||= []).push(m[2]);
  }
  const parts = [];
  for (const [kind, nums] of Object.entries(byKind)) {
    const label = LOC_LABELS[kind] || kind;
    const uniq = [...new Set(nums)];
    parts.push(`${label} ${uniq.join(", ")}`);
  }
  return parts.join(" · ");
}

/**
 * Текст сниппета без внутренних bracket-меток разбиения.
 * "[para 3] Метод обеспечивает..." -> "Метод обеспечивает..."
 */
export function cleanSnippet(text) {
  if (!text) return "";
  return String(text)
    .replace(INLINE_MARKER_RE, " ")
    .replace(/\s{2,}/g, " ")
    .replace(/^\s*[·,;:—-]\s*/, "")
    .trim();
}
