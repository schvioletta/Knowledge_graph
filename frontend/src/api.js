const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function getJson(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

async function throwWithDetail(res) {
  let detail = `${res.status}`;
  try {
    const body = await res.json();
    if (body?.detail) detail = body.detail;
  } catch {
    // тело не JSON — оставляем код статуса
  }
  throw new Error(detail);
}

export const api = {
  fullGraph: () => getJson("/api/graph"),
  node: (id) => getJson(`/api/graph/${encodeURIComponent(id)}`),
  neighbors: (id, depth = 1) => getJson(`/api/graph/${encodeURIComponent(id)}/neighbors?depth=${depth}`),
  search: (q) => getJson(`/api/search?q=${encodeURIComponent(q)}`),
  gaps: (x = "material", y = "regime") => getJson(`/api/gaps?x=${x}&y=${y}`),
  timeline: () => getJson("/api/timeline"),

  listDocuments: () => getJson("/api/documents"),

  uploadDocument: async (file) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/documents/upload`, { method: "POST", body: form });
    if (!res.ok) await throwWithDetail(res);
    return res.json();
  },

  addLink: async (url) => {
    const res = await fetch(`${BASE}/api/documents/link`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) await throwWithDetail(res);
    return res.json();
  },

  ragAsk: (q, autoAttach = true) =>
    getJson(`/api/rag/ask?q=${encodeURIComponent(q)}&auto_attach=${autoAttach}`),

  // Потоковый ответ (SSE). Парсит поток событий text/event-stream вручную
  // через fetch + ReadableStream (а не EventSource) — так можно ловить сетевые
  // ошибки и не тянуть отдельный GET без контроля над отменой. Колбэки:
  //   onEvent({type, ...}) — на каждое событие (thinking/answer_delta/done/error)
  // Возвращает промис, который резолвится по завершении потока.
  ragAskStream: async (q, { onEvent, signal, autoAttach = true } = {}) => {
    const res = await fetch(
      `${BASE}/api/rag/ask/stream?q=${encodeURIComponent(q)}&auto_attach=${autoAttach}`,
      { headers: { Accept: "text/event-stream" }, signal },
    );
    if (!res.ok || !res.body) await throwWithDetail(res);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // SSE-кадры разделены пустой строкой (\n\n); внутри кадра строки data:
    const flushFrame = (frame) => {
      const dataLines = frame
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trimStart());
      if (!dataLines.length) return;
      try {
        onEvent?.(JSON.parse(dataLines.join("\n")));
      } catch {
        // неполный/битый кадр — пропускаем, следующий придёт целым
      }
    };

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        flushFrame(buffer.slice(0, sep));
        buffer = buffer.slice(sep + 2);
      }
    }
    if (buffer.trim()) flushFrame(buffer);
  },

  discoverAndAttach: async (query, topDocs = 5) => {
    const res = await fetch(`${BASE}/api/rag/discover-and-attach`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_docs: topDocs }),
    });
    if (!res.ok) await throwWithDetail(res);
    return res.json();
  },

  deleteDocument: async (id) => {
    const res = await fetch(`${BASE}/api/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (!res.ok) await throwWithDetail(res);
    return res.json();
  },
};
