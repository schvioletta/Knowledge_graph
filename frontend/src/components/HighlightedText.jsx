// Подсветка названий сущностей в ПЛОСКОМ тексте (без markdown) — для сниппетов
// источников. В отличие от AnswerContent (markdown + rehype), здесь простой
// split по regexу из имён сущностей и обёртка совпадений в .source-glow.

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export default function HighlightedText({ text, entities, className = "source-glow" }) {
  if (!text) return null;
  const named = (entities || []).filter((e) => e?.name && e.name.length >= 3);
  if (!named.length) return text;

  // Длинные имена первыми — чтобы «электроэкстракция никеля» матчилась раньше «никель».
  const sorted = [...named].sort((a, b) => b.name.length - a.name.length);
  const nameSet = new Set(sorted.map((e) => e.name.toLowerCase()));
  const regex = new RegExp(`(${sorted.map((e) => escapeRegExp(e.name)).join("|")})`, "giu");

  return text.split(regex).map((part, i) =>
    part && nameSet.has(part.toLowerCase())
      ? <span key={i} className={className}>{part}</span>
      : part,
  );
}
