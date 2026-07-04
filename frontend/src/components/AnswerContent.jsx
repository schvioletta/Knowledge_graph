import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const TYPE_LABEL = {
  material: "материал",
  process: "процесс",
  equipment: "оборудование",
  condition: "условие",
  facility: "предприятие",
  property: "свойство",
  experiment: "эксперимент",
  expert: "эксперт",
  conclusion: "вывод",
  publication: "публикация",
  topic: "тема",
  team: "команда",
};

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Rehype-плагин: разбивает текстовые узлы на совпадения с названиями сущностей,
// оборачивая их в элемент <entity>. Не заходит внутрь code/pre/a — там подсветка
// не нужна и ломала бы разметку. Более длинные названия матчатся раньше вложенных
// (regex собран из имён, отсортированных по длине по убыванию — см. AnswerContent).
function makeHighlightPlugin(regex, entityByName) {
  const SKIP = new Set(["code", "pre", "a"]);
  return () => (tree) => {
    const walk = (node) => {
      if (!node.children || !node.children.length) return;
      const out = [];
      for (const child of node.children) {
        if (child.type === "element" && SKIP.has(child.tagName)) {
          out.push(child);
          continue;
        }
        if (child.type !== "text") {
          walk(child);
          out.push(child);
          continue;
        }
        regex.lastIndex = 0;
        const text = child.value;
        let last = 0;
        let m;
        let matched = false;
        while ((m = regex.exec(text)) !== null) {
          matched = true;
          if (m.index > last) out.push({ type: "text", value: text.slice(last, m.index) });
          const ent = entityByName.get(m[0].toLowerCase());
          out.push({
            type: "element",
            tagName: "entity",
            properties: {
              dataId: ent?.id || "",
              dataName: ent?.name || m[0],
              dataType: ent?.type || "",
              dataMentions: String(ent?.mentions ?? 0),
            },
            children: [{ type: "text", value: m[0] }],
          });
          last = m.index + m[0].length;
          if (m[0].length === 0) regex.lastIndex += 1;
        }
        if (!matched) {
          out.push(child);
        } else if (last < text.length) {
          out.push({ type: "text", value: text.slice(last) });
        }
      }
      node.children = out;
    };
    walk(tree);
  };
}

export default function AnswerContent({ text, entities, onEntityClick, streaming }) {
  const { rehypePlugins, components } = useMemo(() => {
    const named = (entities || []).filter((e) => e.name && e.name.length >= 3);
    if (!named.length) return { rehypePlugins: [], components: BASE_COMPONENTS };

    const byName = new Map();
    for (const e of named) byName.set(e.name.toLowerCase(), e);
    // Длинные названия первыми — чтобы «электроэкстракция никеля» матчилась
    // раньше вложенного «никель» в одной и той же позиции.
    const sorted = [...named].sort((a, b) => b.name.length - a.name.length);
    const pattern = sorted.map((e) => escapeRegExp(e.name)).join("|");
    const regex = new RegExp(pattern, "giu");

    const EntitySpan = ({ node, children }) => {
      const p = node?.properties || {};
      const type = p.dataType || "";
      const mentions = Number(p.dataMentions || 0);
      const label = TYPE_LABEL[type] || type || "сущность";
      const title = `${p.dataName || ""} · ${label}${mentions ? ` · упоминаний: ${mentions}` : ""}`;
      return (
        <span
          className="entity-highlight"
          title={title}
          role="button"
          tabIndex={0}
          onClick={() => p.dataId && onEntityClick?.(p.dataId)}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === " ") && p.dataId) {
              e.preventDefault();
              onEntityClick?.(p.dataId);
            }
          }}
        >
          {children}
        </span>
      );
    };

    return {
      rehypePlugins: [makeHighlightPlugin(regex, byName)],
      components: { ...BASE_COMPONENTS, entity: EntitySpan },
    };
  }, [entities, onEntityClick]);

  return (
    <div className={`kg-markdown text-sm leading-relaxed text-ink ${streaming ? "stream-caret" : ""}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={rehypePlugins} components={components}>
        {text || ""}
      </ReactMarkdown>
    </div>
  );
}

// Компактная типографика внутри узкой панели результатов: markdown по умолчанию
// даёт крупные отступы/заголовки, здесь они прижаты под размер блока.
const BASE_COMPONENTS = {
  h1: (p) => <h3 className="mt-3 mb-1.5 text-base font-semibold text-ink" {...p} />,
  h2: (p) => <h3 className="mt-3 mb-1.5 text-sm font-semibold text-ink" {...p} />,
  h3: (p) => <h4 className="mt-2.5 mb-1 text-sm font-semibold text-ink/90" {...p} />,
  p: (p) => <p className="my-1.5" {...p} />,
  ul: (p) => <ul className="my-1.5 list-disc space-y-0.5 pl-5" {...p} />,
  ol: (p) => <ol className="my-1.5 list-decimal space-y-0.5 pl-5" {...p} />,
  li: (p) => <li className="marker:text-ink/40" {...p} />,
  a: (p) => <a className="text-primary underline underline-offset-2 hover:text-primary/80" target="_blank" rel="noreferrer" {...p} />,
  blockquote: (p) => <blockquote className="my-2 border-l-2 border-primary/40 pl-3 text-ink/70 italic" {...p} />,
  code: (p) => <code className="rounded bg-ink/10 px-1 py-0.5 text-[0.85em] text-secondary" {...p} />,
  table: (p) => <div className="my-2 overflow-x-auto"><table className="w-full border-collapse text-xs" {...p} /></div>,
  th: (p) => <th className="border border-ink/15 bg-ink/5 px-2 py-1 text-left font-semibold" {...p} />,
  td: (p) => <td className="border border-ink/10 px-2 py-1 align-top" {...p} />,
};
