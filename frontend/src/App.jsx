import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { PanelLeftClose, PanelLeftOpen, RotateCcw } from "lucide-react";
import GraphView from "./components/GraphView";
import SearchBar from "./components/SearchBar";
import SourcesPanel from "./components/SourcesPanel";
import ResultsPanel from "./components/ResultsPanel";
import HistoryPanel from "./components/HistoryPanel";
import FilterDock from "./components/FilterDock";
import NavBar from "./components/NavBar";
import Footer from "./components/Footer";
import ProblemCards from "./sections/ProblemCards";
import Pipeline from "./sections/Pipeline";
import Capabilities from "./sections/Capabilities";
import Coverage from "./sections/Coverage";
import RequirementsStatus from "./sections/RequirementsStatus";
import Architecture from "./sections/Architecture";
import { api } from "./api";
import { FILTERABLE_TYPES } from "./constants";

const HISTORY_STORAGE_KEY = "kg-rag-history";
const HISTORY_LIMIT = 50;

const RESULTS_HEIGHT_KEY = "kg-results-height";
const RESULTS_HEIGHT_DEFAULT = 380;
const RESULTS_HEIGHT_MIN = 240;
const RESULTS_HEIGHT_MAX = 900;

function loadResultsHeight() {
  const v = parseInt(localStorage.getItem(RESULTS_HEIGHT_KEY), 10);
  return Number.isFinite(v) && v >= RESULTS_HEIGHT_MIN && v <= RESULTS_HEIGHT_MAX
    ? v
    : RESULTS_HEIGHT_DEFAULT;
}

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

// crypto.randomUUID() недоступен по HTTP с IP (не secure context); fallback для истории.
function newHistoryId() {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function mergeVis(nodesMap, links, vis) {
  const newNodesMap = { ...nodesMap };
  for (const n of vis.nodes) {
    newNodesMap[n.id] = { ...newNodesMap[n.id], ...n };
  }
  const linkKey = (l) => `${l.source}::${l.target}::${l.type}`;
  const existingKeys = new Set(links.map(linkKey));
  const newLinks = [...links];
  for (const l of vis.links) {
    const k = linkKey(l);
    if (!existingKeys.has(k)) {
      existingKeys.add(k);
      newLinks.push(l);
    }
  }
  return [newNodesMap, newLinks];
}

function applyChunkGraphToState(r, setNodesMap, setLinks, setHighlightIds, setFitSignal) {
  if (r?.chunk_graph?.nodes?.length) {
    const nm = {};
    for (const n of r.chunk_graph.nodes) nm[n.id] = n;
    setNodesMap(nm);
    setLinks(r.chunk_graph.links.map((l) => ({ ...l })));
    setHighlightIds(new Set(r.chunk_graph_node_ids || []));
  } else {
    setNodesMap({});
    setLinks([]);
    setHighlightIds(new Set());
  }
  setFitSignal((s) => s + 1);
}

export default function App() {
  const [nodesMap, setNodesMap] = useState({});
  const [links, setLinks] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [detail, setDetail] = useState(null);
  const [highlightIds, setHighlightIds] = useState(new Set());
  const [searchLoading, setSearchLoading] = useState(false);
  const [fitSignal, setFitSignal] = useState(0);

  const [gapEnabled, setGapEnabled] = useState(false);
  const [gapX, setGapX] = useState("material");
  const [gapY, setGapY] = useState("condition");
  const [gapNodes, setGapNodes] = useState([]);
  const [gapLinks, setGapLinks] = useState([]);

  const [timelineEnabled, setTimelineEnabled] = useState(false);
  const [timelineDates, setTimelineDates] = useState([]);
  const [cursor, setCursor] = useState(0);

  const [typeFilter, setTypeFilter] = useState(() => new Set(FILTERABLE_TYPES));
  const [filterOpen, setFilterOpen] = useState(true);
  const [resultsTab, setResultsTab] = useState("documents");

  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [linkSubmitting, setLinkSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [sourceError, setSourceError] = useState("");
  const [sourceNotice, setSourceNotice] = useState("");
  const [ragResult, setRagResult] = useState(null);
  const [ragLoading, setRagLoading] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [thinkingSteps, setThinkingSteps] = useState([]);
  const [streamAnswer, setStreamAnswer] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [liveEntities, setLiveEntities] = useState([]);

  const [history, setHistory] = useState(loadHistory);
  const [activeHistoryId, setActiveHistoryId] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [resultsHeight, setResultsHeight] = useState(loadResultsHeight);

  // Блок результатов («По документам») — для авто-перехода после «Спросить».
  const resultsRef = useRef(null);

  useEffect(() => {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history));
  }, [history]);

  useEffect(() => {
    localStorage.setItem(RESULTS_HEIGHT_KEY, String(resultsHeight));
  }, [resultsHeight]);

  const refreshDocuments = () => api.listDocuments().then(setDocuments);

  useEffect(() => {
    api.fullGraph().then((vis) => {
      const [nm, ls] = mergeVis({}, [], vis);
      setNodesMap(nm);
      setLinks(ls);
      setFitSignal((s) => s + 1);
    });
    api.timeline().then(setTimelineDates);
    refreshDocuments();
  }, []);

  useEffect(() => {
    if (!gapEnabled) {
      setGapNodes([]);
      setGapLinks([]);
      return;
    }
    api.gaps(gapX, gapY).then((data) => {
      const ghosts = [];
      const ghostLinks = [];
      for (const gap of data.gaps) {
        const ghostId = `ghost::${gap.x_id}::${gap.y_id}`;
        ghosts.push({
          id: ghostId,
          type: "ghost",
          name: `${gap.x_name} × ${gap.y_name}`,
          degree: 1,
          attrs: {},
        });
        ghostLinks.push({ source: gap.x_id, target: ghostId, type: "GAP" });
        ghostLinks.push({ source: gap.y_id, target: ghostId, type: "GAP" });
      }
      setGapNodes(ghosts);
      setGapLinks(ghostLinks);
    });
  }, [gapEnabled, gapX, gapY]);

  const graphData = useMemo(() => {
    let allNodes = Object.values(nodesMap);
    let allLinks = links;

    if (gapEnabled) {
      allNodes = [...allNodes, ...gapNodes];
      allLinks = [...allLinks, ...gapLinks];
    }

    if (timelineEnabled && timelineDates.length > 0) {
      const cutoff = timelineDates[Math.min(cursor, timelineDates.length - 1)]?.date;
      const datedIds = new Set(timelineDates.map((d) => d.id));
      const visibleIds = new Set(
        allNodes
          .filter((n) => !datedIds.has(n.id) || (n.attrs?.date && n.attrs.date <= cutoff))
          .map((n) => n.id)
      );
      allNodes = allNodes.filter((n) => visibleIds.has(n.id));
      allLinks = allLinks.filter((l) => {
        const s = l.source.id ?? l.source;
        const t = l.target.id ?? l.target;
        return visibleIds.has(s) && visibleIds.has(t);
      });
    }

    if (typeFilter.size < FILTERABLE_TYPES.length) {
      const visibleIds = new Set(
        allNodes.filter((n) => n.type === "ghost" || typeFilter.has(n.type)).map((n) => n.id)
      );
      allNodes = allNodes.filter((n) => visibleIds.has(n.id));
      allLinks = allLinks.filter((l) => {
        const s = l.source.id ?? l.source;
        const t = l.target.id ?? l.target;
        return visibleIds.has(s) && visibleIds.has(t);
      });
    }

    return { nodes: allNodes, links: allLinks.map((l) => ({ ...l })) };
  }, [nodesMap, links, gapEnabled, gapNodes, gapLinks, timelineEnabled, timelineDates, cursor, typeFilter]);

  const handleNodeClick = async (node) => {
    setSelectedNode(node);
    setHighlightIds(new Set());
    if (node.type === "ghost") {
      setDetail(null);
      return;
    }
    setResultsTab("schema");
    if (String(node.id).startsWith("rg_")) {
      setDetail(null);
      return;
    }
    const d = await api.node(node.id);
    setDetail(d);
  };

  const handleExpand = async (nodeId) => {
    if (String(nodeId).startsWith("rg_")) return;
    const vis = await api.neighbors(nodeId, 1);
    setNodesMap((prev) => mergeVis(prev, links, vis)[0]);
    setLinks((prev) => mergeVis(nodesMap, prev, vis)[1]);
  };

  const handleUpload = async (file) => {
    setUploading(true);
    setSourceError("");
    setSourceNotice("");
    try {
      const doc = await api.uploadDocument(file);
      // Дубликат по содержимому (см. backend/rag/store.py) — эмбеддинги не
      // пересчитывались, файл не сохранялся повторно; сообщаем явно, чтобы
      // не выглядело так, будто загрузка молча ничего не сделала.
      if (doc.duplicate) {
        setSourceNotice(`«${doc.title}» уже есть в базе — повторно не обрабатывали.`);
      }
      await refreshDocuments();
    } catch (e) {
      setSourceError(e.message || "Не удалось загрузить файл");
    } finally {
      setUploading(false);
    }
  };

  const handleAddLink = async (url) => {
    setLinkSubmitting(true);
    setSourceError("");
    setSourceNotice("");
    try {
      const doc = await api.addLink(url);
      if (doc.duplicate) {
        setSourceNotice(`«${doc.title}» уже есть в базе — повторно не обрабатывали.`);
      }
      await refreshDocuments();
    } catch (e) {
      setSourceError(e.message || "Не удалось добавить ссылку");
    } finally {
      setLinkSubmitting(false);
    }
  };

  const handleDeleteDocument = async (id) => {
    setDeletingId(id);
    setSourceError("");
    try {
      await api.deleteDocument(id);
      await refreshDocuments();
    } catch (e) {
      setSourceError(e.message || "Не удалось удалить источник");
    } finally {
      setDeletingId(null);
    }
  };

  const handleHighlightChain = (nodeIds) => {
    if (!nodeIds?.length) return;
    setHighlightIds(new Set(nodeIds));
    setFitSignal((s) => s + 1);
  };

  const handleSearch = async (question) => {
    setSearchLoading(true);
    setRagLoading(true);
    setStreaming(true);
    setGapEnabled(false);
    setCurrentQuestion(question);
    setActiveHistoryId(null);
    setSelectedNode(null);
    setDetail(null);
    setRagResult(null);
    setThinkingSteps([]);
    setStreamAnswer("");
    setLiveEntities([]);
    setResultsTab("documents");

    // Авто-переход к области результатов: плавно прокручиваем к блоку
    // «По документам» и переводим на него фокус, чтобы пользователь сразу видел
    // Thinking и последующий ответ, не ища область результатов вручную. rAF —
    // чтобы прокрутка сработала после того, как React применит сброс состояния.
    requestAnimationFrame(() => {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      resultsRef.current?.focus({ preventScroll: true });
    });

    const steps = [];
    try {
      await api.ragAskStream(question, {
        onEvent: (ev) => {
          if (ev.type === "thinking") {
            steps.push({ stage: ev.stage, text: ev.text });
            setThinkingSteps([...steps]);
            if (ev.entities) setLiveEntities(ev.entities);
          } else if (ev.type === "answer_delta") {
            setStreamAnswer((prev) => prev + ev.text);
          } else if (ev.type === "done") {
            const r = ev.result;
            setRagResult(r);
            applyChunkGraphToState(r, setNodesMap, setLinks, setHighlightIds, setFitSignal);
            const entry = {
              id: newHistoryId(), question, timestamp: Date.now(),
              ragResult: r, thinkingSteps: [...steps],
            };
            setHistory((prev) => [entry, ...prev].slice(0, HISTORY_LIMIT));
            setActiveHistoryId(entry.id);
          } else if (ev.type === "error") {
            steps.push({ stage: "error", text: `Ошибка: ${ev.text}` });
            setThinkingSteps([...steps]);
          }
        },
      });
      await refreshDocuments();
    } catch {
      setRagResult(null);
      applyChunkGraphToState(null, setNodesMap, setLinks, setHighlightIds, setFitSignal);
    } finally {
      setSearchLoading(false);
      setRagLoading(false);
      setStreaming(false);
    }
  };

  const handleEntityClick = (nodeId) => {
    if (!nodeId) return;
    setHighlightIds(new Set([nodeId]));
    setFitSignal((s) => s + 1);
  };

  // Вертикальный ресайз блока результатов (история | по документам | схема графа).
  // Тянем нижний drag-handle; высота применяется к grid'у сразу (колонки h-full
  // следуют за ним), клампится и сохраняется в localStorage (см. эффект выше).
  const startResultsResize = (e) => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = resultsHeight;
    const onMove = (ev) => {
      const next = Math.min(
        RESULTS_HEIGHT_MAX,
        Math.max(RESULTS_HEIGHT_MIN, startH + (ev.clientY - startY)),
      );
      setResultsHeight(next);
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
    };
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const handleHistorySelect = (entry) => {
    setRagResult(entry.ragResult);
    setCurrentQuestion(entry.question);
    setActiveHistoryId(entry.id);
    setResultsTab("documents");
    setStreaming(false);
    setStreamAnswer("");
    setThinkingSteps(entry.thinkingSteps || []);
    setLiveEntities(entry.ragResult?.highlight_entities || []);
    applyChunkGraphToState(entry.ragResult, setNodesMap, setLinks, setHighlightIds, setFitSignal);
    setSelectedNode(null);
    setDetail(null);
  };

  const handleHistoryDelete = (id) => {
    setHistory((prev) => prev.filter((h) => h.id !== id));
    if (activeHistoryId === id) setActiveHistoryId(null);
  };

  const handleHistoryClear = () => {
    setHistory([]);
    setActiveHistoryId(null);
  };

  const toggleType = (type) => {
    setTypeFilter((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const resetTypes = () => setTypeFilter(new Set(FILTERABLE_TYPES));

  return (
    <div id="top" className="min-h-screen text-ink">
      <NavBar />

      <section id="workbench" className="border-b border-ink/10">
        {/* Masthead — структурный навигационный блок, не декоративный hero.
            Без своего bg-bg — здесь должен просвечивать фирменный градиент body. */}
        <div>
          <div className="mx-auto max-w-[1600px] px-6 py-12 md:py-16">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: "easeOut" }}
            >
              <span className="text-xs font-semibold uppercase tracking-[0.2em] text-ink/70">
                Knowledge Graph · R&D
              </span>
              <h1 className="mt-3 max-w-2xl text-3xl font-bold leading-[1.15] text-ink md:text-4xl lg:text-5xl">
                Knowledge Graph для R&D горно-металлургической отрасли
              </h1>
              <p className="mt-3 max-w-xl text-sm text-ink/70 md:text-base">
                Единая интеллектуальная карта исследований, экспериментов, публикаций,
                технологий и экспертов.
              </p>
            </motion.div>
          </div>
        </div>

        {/* Toolbar поиска — только строка поиска; ответ живёт в панели результатов
            под графом (вкладка «По документам»), не над input. */}
        <div id="search-toolbar" className="border-b border-ink/10 px-6 py-4">
          <div className="mx-auto flex max-w-[1600px] flex-col gap-3">
            <SearchBar onSearch={handleSearch} loading={searchLoading} />
            <SourcesPanel
              documents={documents}
              onUpload={handleUpload}
              onAddLink={handleAddLink}
              onDelete={handleDeleteDocument}
              deletingId={deletingId}
              uploading={uploading}
              linkSubmitting={linkSubmitting}
              error={sourceError}
              notice={sourceNotice}
            />
          </div>
        </div>

        <div className="mx-auto max-w-[1600px]">
          {/* Блок результатов (История запросов | По документам | Схема графа) —
              НАД фильтрами и графом. Высоту задаёт пользователь: вертикальный
              ресайз нижним drag-handle, значение сохраняется в localStorage.
              Inline-height на grid — колонки h-full тянутся за ним синхронно;
              собственная ограниченная высота + overflow-hidden структурно
              исключают влияние длинного ответа на layout графа ниже. */}
          <div
            ref={resultsRef}
            tabIndex={-1}
            aria-label="Результаты по документам"
            className="scroll-mt-4 border-t border-ink/10 p-4 outline-none focus:outline-none focus-visible:outline-none"
          >
            <div
              style={{ height: resultsHeight }}
              className={`grid w-full overflow-hidden rounded-md border border-ink/10 ${
                historyOpen ? "lg:grid-cols-[240px_1fr]" : "lg:grid-cols-[44px_1fr]"
              }`}
            >
              <div className="hidden border-r border-ink/10 lg:flex lg:h-full lg:min-h-0 lg:flex-col lg:overflow-hidden">
                <div className="flex shrink-0 items-center justify-between border-b border-ink/10 px-2 py-2">
                  {historyOpen && (
                    <span className="pl-1.5 text-[11px] font-semibold uppercase tracking-[0.15em] text-ink/60">
                      История запросов
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => setHistoryOpen((v) => !v)}
                    aria-label={historyOpen ? "Свернуть панель истории" : "Развернуть панель истории"}
                    aria-expanded={historyOpen}
                    className="ml-auto rounded p-1.5 text-ink/60 transition hover:bg-ink/5 hover:text-ink"
                  >
                    {historyOpen ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}
                  </button>
                </div>
                {historyOpen && (
                  <div className="min-h-0 flex-1 overflow-y-auto">
                    <HistoryPanel
                      history={history}
                      activeId={activeHistoryId}
                      onSelect={handleHistorySelect}
                      onDelete={handleHistoryDelete}
                      onClear={handleHistoryClear}
                    />
                  </div>
                )}
              </div>

              <div className="min-h-0 min-w-0 overflow-hidden">
                <ResultsPanel
                  activeTab={resultsTab}
                  onTabChange={setResultsTab}
                  question={currentQuestion}
                  ragResult={ragResult}
                  ragLoading={ragLoading}
                  thinkingSteps={thinkingSteps}
                  streamAnswer={streamAnswer}
                  streaming={streaming}
                  liveEntities={liveEntities}
                  onEntityClick={handleEntityClick}
                  node={selectedNode}
                  detail={detail}
                  onExpand={handleExpand}
                  onClose={() => { setSelectedNode(null); setDetail(null); }}
                  onHighlightChain={handleHighlightChain}
                />
              </div>
            </div>

            {/* Нижний drag-handle вертикального ресайза — тянет высоту всех трёх
                колонок сразу (см. startResultsResize / resultsHeight). */}
            <div
              role="separator"
              aria-orientation="horizontal"
              aria-label="Изменить высоту блока результатов"
              title="Потяните, чтобы изменить высоту"
              onMouseDown={startResultsResize}
              className="group mt-1 flex h-3 w-full cursor-ns-resize items-center justify-center rounded"
            >
              <div className="h-1 w-10 rounded-full bg-ink/20 transition group-hover:bg-primary/60" />
            </div>
          </div>

          {/* История на мобильных — на десктопе она уже колонкой в сетке выше */}
          <div className="border-t border-ink/10 p-4 lg:hidden">
            <div className="h-[220px] overflow-hidden rounded-md border border-ink/10">
              <HistoryPanel
                history={history}
                activeId={activeHistoryId}
                onSelect={handleHistorySelect}
                onDelete={handleHistoryDelete}
                onClear={handleHistoryClear}
              />
            </div>
          </div>

          {/* Дашборд: фильтры (сворачиваемая панель) | граф — фиксированной высоты
              h-[640px]. Панель результатов сознательно ВНЕ этой сетки (выше):
              раньше она была третьей колонкой той же grid-строки, и длинный ответ
              (особенно RAG-ответ с цитатами) раздувал высоту всей строки через
              классический CSS grid min-height:auto — из-за этого «плыл» весь
              граф. Отдельный блок с собственной высотой структурно исключает этот
              баг: контент ответа не влияет на размеры графа. */}
          <div
            className={`grid h-[640px] w-full ${
              filterOpen ? "lg:grid-cols-[280px_1fr]" : "lg:grid-cols-[44px_1fr]"
            }`}
          >
            <div className="hidden border-r border-ink/10 lg:flex lg:h-full lg:min-h-0 lg:flex-col lg:overflow-hidden">
              <div className="flex shrink-0 items-center justify-between border-b border-ink/10 px-2 py-2">
                {filterOpen && (
                  <span className="pl-1.5 text-[11px] font-semibold uppercase tracking-[0.15em] text-ink/60">
                    Фильтры
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => setFilterOpen((v) => !v)}
                  aria-label={filterOpen ? "Свернуть панель фильтров" : "Развернуть панель фильтров"}
                  aria-expanded={filterOpen}
                  className="ml-auto rounded p-1.5 text-ink/60 transition hover:bg-ink/5 hover:text-ink"
                >
                  {filterOpen ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}
                </button>
              </div>
              {filterOpen && (
                <div className="min-h-0 flex-1 overflow-y-auto">
                  <FilterDock
                    typeFilter={typeFilter}
                    onToggleType={toggleType}
                    onResetTypes={resetTypes}
                    gapProps={{
                      enabled: gapEnabled,
                      onToggle: (v) => { setGapEnabled(v); if (v) { setHighlightIds(new Set()); } },
                      xAxis: gapX,
                      yAxis: gapY,
                      onAxisChange: (x, y) => { setGapX(x); setGapY(y); },
                      gapCount: gapNodes.length,
                    }}
                    timelineProps={{
                      enabled: timelineEnabled,
                      onToggle: (v) => { setTimelineEnabled(v); if (v) { setHighlightIds(new Set()); } },
                      dates: timelineDates,
                      cursor,
                      onCursorChange: setCursor,
                    }}
                  />
                </div>
              )}
            </div>

            <div className="relative min-h-0 min-w-0 overflow-hidden border-ink/10">
              {highlightIds.size > 0 && (
                <button
                  type="button"
                  onClick={() => setHighlightIds(new Set())}
                  className="absolute right-2 top-2 z-10 flex items-center gap-1.5 rounded border border-ink/20 bg-surface-deep/90 px-2 py-1 text-xs text-ink/70 backdrop-blur transition hover:border-primary/50 hover:text-ink"
                >
                  <RotateCcw size={12} />
                  Сбросить подсветку
                </button>
              )}
              <GraphView
                graphData={graphData}
                highlightNodeIds={highlightIds}
                onNodeClick={handleNodeClick}
                selectedNodeId={selectedNode?.id}
                fitSignal={fitSignal}
              />
            </div>
          </div>

          {/* Фильтры на мобильных — на десктопе они уже показаны колонкой в сетке выше */}
          <div className="border-t border-ink/10 p-4 lg:hidden">
            <FilterDock
              typeFilter={typeFilter}
              onToggleType={toggleType}
              onResetTypes={resetTypes}
              gapProps={{
                enabled: gapEnabled,
                onToggle: (v) => { setGapEnabled(v); if (v) { setHighlightIds(new Set()); } },
                xAxis: gapX,
                yAxis: gapY,
                onAxisChange: (x, y) => { setGapX(x); setGapY(y); },
                gapCount: gapNodes.length,
              }}
              timelineProps={{
                enabled: timelineEnabled,
                onToggle: (v) => { setTimelineEnabled(v); if (v) { setHighlightIds(new Set()); } },
                dates: timelineDates,
                cursor,
                onCursorChange: setCursor,
              }}
            />
          </div>

        </div>
      </section>

      <ProblemCards />
      <Pipeline />
      <Capabilities />
      <Coverage nodesMap={nodesMap} />
      <RequirementsStatus />
      <Architecture />
      <Footer />
    </div>
  );
}
