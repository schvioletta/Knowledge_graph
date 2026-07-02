import { useEffect, useMemo, useState } from "react";
import GraphView from "./components/GraphView";
import SearchBar from "./components/SearchBar";
import DetailPanel from "./components/DetailPanel";
import GapToggle from "./components/GapToggle";
import TimelineSlider from "./components/TimelineSlider";
import { api } from "./api";
import { TYPE_COLOR, TYPE_LABEL } from "./constants";
import "./app-style.css";

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

    return { nodes: allNodes, links: allLinks.map((l) => ({ ...l })) };
  }, [nodesMap, links, gapEnabled, gapNodes, gapLinks, timelineEnabled, timelineDates, cursor]);

  const handleNodeClick = async (node) => {
    setSelectedNode(node);
    setHighlightIds(new Set());
    setAnswer("");
    if (node.type === "ghost") {
      setDetail(null);
      return;
    }
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
      setFitSignal((s) => s + 1);
    } finally {
      setSearchLoading(false);
    }
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>R&D Knowledge Graph · Горно-металлургическая отрасль</h1>
        <p>Публикации, эксперименты, материалы, процессы, условия, оборудование, предприятия и команды — в одном графе</p>
      </header>

      <div className="app-body">
        <div className="graph-area">
          <SearchBar onSearch={handleSearch} loading={searchLoading} />
          {answer && (
            <div className="answer-box">
              <div className="answer-title">Ответ по графу</div>
              <pre>{answer}</pre>
              <button onClick={() => { setAnswer(""); setHighlightIds(new Set()); }}>Сбросить подсветку</button>
            </div>
          )}
          <div className="controls-row">
            <GapToggle
              enabled={gapEnabled}
              onToggle={(v) => { setGapEnabled(v); if (v) { setHighlightIds(new Set()); setAnswer(""); } }}
              xAxis={gapX}
              yAxis={gapY}
              onAxisChange={(x, y) => { setGapX(x); setGapY(y); }}
              gapCount={gapNodes.length}
            />
            <TimelineSlider
              enabled={timelineEnabled}
              onToggle={(v) => { setTimelineEnabled(v); if (v) { setHighlightIds(new Set()); setAnswer(""); } }}
              dates={timelineDates}
              cursor={cursor}
              onCursorChange={setCursor}
            />
          </div>
          <div className="graph-canvas-wrap">
            <GraphView
              graphData={graphData}
              highlightNodeIds={highlightIds}
              onNodeClick={handleNodeClick}
              selectedNodeId={selectedNode?.id}
              fitSignal={fitSignal}
            />
          </div>
          <Legend />
        </div>
        <DetailPanel
          node={selectedNode}
          detail={detail}
          onExpand={handleExpand}
          onClose={() => { setSelectedNode(null); setDetail(null); }}
        />
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="legend">
      {Object.entries(TYPE_LABEL).map(([type, label]) => (
        <span key={type} className="legend-item">
          <span className="legend-dot" style={{ background: TYPE_COLOR[type] }} />
          {label}
        </span>
      ))}
    </div>
  );
}
