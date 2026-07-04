const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function safeFilename(question) {
  const base = (question || "answer")
    .trim()
    .slice(0, 60)
    .replace(/[^\p{L}\p{N}\- ]/gu, "")
    .replace(/\s+/g, "_");
  return base || "answer";
}

const EXPAND_LLM_EXPORT = {
  ollama: "Qwen (локально)",
  gigachat: "GigaChat (облако)",
};

export function exportAsJson({ question, result }) {
  const payload = {
    question,
    answer: result.answer,
    confidence: result.confidence,
    grounded: result.grounded,
    llm_used: result.llm_used,
    query_original: result.query_original,
    query_expansions: result.query_expansions,
    expand_llm: result.expand_llm,
    chunk_graph_stats: result.chunk_graph_stats,
    experiment_chains: result.experiment_chains,
    citations: result.citations,
    exported_at: new Date().toISOString(),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  triggerDownload(blob, `${safeFilename(question)}.json`);
}

export function exportAsMarkdown({ question, result }) {
  const lines = [
    "# Ответ по загруженным документам",
    "",
    `**Вопрос:** ${question}`,
    "",
    `**Достоверность:** ${result.confidence}${
      result.grounded && !result.llm_used ? " _(без LLM-синтеза — фрагменты источников)_" : ""
    }`,
    "",
  ];
  if (result.query_expansions?.length) {
    lines.push("**Расширенные формулировки поиска:**");
    if (result.expand_llm && EXPAND_LLM_EXPORT[result.expand_llm]) {
      lines.push(`**Источник:** ${EXPAND_LLM_EXPORT[result.expand_llm]}`);
    }
    result.query_expansions.forEach((q) => lines.push(`- ${q}`));
    lines.push("");
  }
  if (result.chunk_graph_stats) {
    const s = result.chunk_graph_stats;
    lines.push(
      `**Граф из фрагментов:** ${s.entities} сущностей, ${s.relations} связей, ${s.chunks} чанков`,
    );
    lines.push("");
  }
  if (result.experiment_chains?.length) {
    lines.push("**Цепочки (материал → процесс → оборудование → результат):**", "");
    for (const chain of result.experiment_chains) {
      const parts = chain.steps.map((step) => {
        const names = step.items?.map((i) => i.name).filter(Boolean).join(", ");
        return names || "—";
      });
      const header = chain.publication?.name
        ? `${chain.publication.name} · ${chain.experiment_name || "Эксперимент"}`
        : (chain.experiment_name || "Эксперимент");
      lines.push(`- **${header}:** ${parts.join(" → ")}`);
    }
    lines.push("");
  }
  lines.push(
    "## Ответ",
    "",
    result.answer,
    "",
  );
  if (result.citations?.length) {
    lines.push("## Источники", "");
    for (const c of result.citations) {
      const score = c.score != null ? ` _(сходство ${c.score})_` : "";
      lines.push(`${c.index}. **${c.title}** — ${c.location}${score}`);
      if (c.snippet) lines.push(`   > ${c.snippet.replace(/\n/g, " ")}`);
      lines.push("");
    }
  }
  const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
  triggerDownload(blob, `${safeFilename(question)}.md`);
}

export async function exportAsPdf({ question, result }) {
  const res = await fetch(`${BASE}/api/rag/export/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      answer: result.answer,
      confidence: result.confidence,
      citations: result.citations,
      grounded: result.grounded,
      llm_used: result.llm_used,
    }),
  });
  if (!res.ok) throw new Error(`Экспорт в PDF не удался (${res.status})`);
  const blob = await res.blob();
  triggerDownload(blob, `${safeFilename(question)}.pdf`);
}
