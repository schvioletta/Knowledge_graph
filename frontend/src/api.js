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

  ragAsk: (q) => getJson(`/api/rag/ask?q=${encodeURIComponent(q)}`),

  sourceFileUrl: (fileUrlOrName) => {
    if (!fileUrlOrName) return null;
    if (fileUrlOrName.startsWith("http")) return fileUrlOrName;
    if (fileUrlOrName.startsWith("/api/")) return `${BASE}${fileUrlOrName}`;
    return `${BASE}/api/sources/file?name=${encodeURIComponent(fileUrlOrName)}`;
  },
};
