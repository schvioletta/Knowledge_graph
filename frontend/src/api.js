const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function getJson(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  fullGraph: () => getJson("/api/graph"),
  node: (id) => getJson(`/api/graph/${encodeURIComponent(id)}`),
  neighbors: (id, depth = 1) => getJson(`/api/graph/${encodeURIComponent(id)}/neighbors?depth=${depth}`),
  search: (q) => getJson(`/api/search?q=${encodeURIComponent(q)}`),
  gaps: (x = "material", y = "regime") => getJson(`/api/gaps?x=${x}&y=${y}`),
  timeline: () => getJson("/api/timeline"),
};
