import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import GraphView from "./components/GraphView";
import SearchBar from "./components/SearchBar";
import ResultsPanel from "./components/ResultsPanel";
import FilterDock from "./components/FilterDock";
import NavBar from "./components/NavBar";
import Footer from "./components/Footer";
import ProblemCards from "./sections/ProblemCards";
import Pipeline from "./sections/Pipeline";
import Capabilities from "./sections/Capabilities";
import Coverage from "./sections/Coverage";
import ExampleQueries from "./sections/ExampleQueries";
import RequirementsStatus from "./sections/RequirementsStatus";
import Architecture from "./sections/Architecture";
import { api } from "./api";
import { FILTERABLE_TYPES } from "./constants";

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

export default function App() {
  const [nodesMap, setNodesMap] = useState({});
  const [links, setLinks] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [detail, setDetail] = useState(null);
  const [highlightIds, setHighlightIds] = useState(new Set());
  const [answer, setAnswer] = useState("");
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
  const [resultsTab, setResultsTab] = useState("answer");

  useEffect(() => {
    api.fullGraph().then((vis) => {
      const [nm, ls] = mergeVis({}, [], vis);
      setNodesMap(nm);
      setLinks(ls);
      setFitSignal((s) => s + 1);
    });
    api.timeline().then(setTimelineDates);
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
    const d = await api.node(node.id);
    setDetail(d);
  };

  const handleExpand = async (nodeId) => {
    const vis = await api.neighbors(nodeId, 1);
    setNodesMap((prev) => mergeVis(prev, links, vis)[0]);
    setLinks((prev) => mergeVis(nodesMap, prev, vis)[1]);
  };

  const handleSearch = async (question) => {
    setSearchLoading(true);
    setGapEnabled(false);
    try {
      const result = await api.search(question);
      setNodesMap((prev) => mergeVis(prev, links, result.subgraph)[0]);
      setLinks((prev) => mergeVis(nodesMap, prev, result.subgraph)[1]);
      setHighlightIds(new Set(result.path_node_ids));
      setAnswer(result.answer);
      setSelectedNode(null);
      setDetail(null);
      setResultsTab("answer");
      setFitSignal((s) => s + 1);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleExampleSelect = (question) => {
    document.getElementById("workbench")?.scrollIntoView({ behavior: "smooth" });
    handleSearch(question);
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
    <div id="top" className="min-h-screen bg-bg text-ink">
      <NavBar />

      <section id="workbench" className="border-b border-ink/10">
        {/* Masthead — структурный навигационный блок, не декоративный hero */}
        <div className="bg-bg">
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
              <div className="mt-6 flex flex-wrap gap-3">
                <a
                  href="#search-toolbar"
                  className="rounded bg-primary px-5 py-2.5 text-sm font-semibold text-bg transition hover:brightness-110"
                >
                  Попробовать поиск
                </a>
                <a
                  href="#examples"
                  className="rounded border border-ink/30 px-5 py-2.5 text-sm font-semibold text-ink transition hover:border-ink/60"
                >
                  Посмотреть демо
                </a>
              </div>
            </motion.div>
          </div>
        </div>

        {/* Toolbar поиска — только строка поиска; ответ теперь живёт в правой
            панели результатов (вкладка «Текстовый ответ»), не над input. */}
        <div id="search-toolbar" className="border-b border-ink/10 bg-bg px-6 py-4">
          <div className="mx-auto max-w-[1600px]">
            <SearchBar onSearch={handleSearch} loading={searchLoading} />
          </div>
        </div>

        {/* Дашборд: фильтры (сворачиваемая панель) | граф | результаты */}
        <div className="mx-auto max-w-[1600px]">
          <div
            className={`grid h-[640px] w-full transition-[grid-template-columns] duration-200 ${
              filterOpen ? "lg:grid-cols-[280px_1fr_360px]" : "lg:grid-cols-[44px_1fr_360px]"
            }`}
          >
            <div className="hidden border-r border-ink/10 lg:flex lg:h-full lg:flex-col lg:overflow-hidden">
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

            <div className="min-h-[420px] min-w-0 overflow-hidden border-ink/10 lg:border-r">
              <GraphView
                graphData={graphData}
                highlightNodeIds={highlightIds}
                onNodeClick={handleNodeClick}
                selectedNodeId={selectedNode?.id}
                fitSignal={fitSignal}
              />
            </div>

            <div className="hidden border-l border-ink/10 lg:block">
              <ResultsPanel
                activeTab={resultsTab}
                onTabChange={setResultsTab}
                answer={answer}
                onResetHighlight={() => { setAnswer(""); setHighlightIds(new Set()); }}
                node={selectedNode}
                detail={detail}
                onExpand={handleExpand}
                onClose={() => { setSelectedNode(null); setDetail(null); }}
              />
            </div>
          </div>

          {/* Стековая раскладка для узких экранов: фильтры и результаты под канвасом */}
          <div className="flex flex-col gap-4 border-t border-ink/10 p-4 lg:hidden">
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
            <div className="h-[420px] overflow-hidden rounded-md border border-ink/10">
              <ResultsPanel
                activeTab={resultsTab}
                onTabChange={setResultsTab}
                answer={answer}
                onResetHighlight={() => { setAnswer(""); setHighlightIds(new Set()); }}
                node={selectedNode}
                detail={detail}
                onExpand={handleExpand}
                onClose={() => { setSelectedNode(null); setDetail(null); }}
              />
            </div>
          </div>
        </div>
      </section>

      <ProblemCards />
      <Pipeline />
      <Capabilities />
      <Coverage nodesMap={nodesMap} />
      <ExampleQueries onSelect={handleExampleSelect} />
      <RequirementsStatus />
      <Architecture />
      <Footer />
    </div>
  );
}
