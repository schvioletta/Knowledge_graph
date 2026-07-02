import { useCallback, useEffect, useRef } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { TYPE_COLOR } from "../constants";

export default function GraphView({
  graphData,
  highlightNodeIds,
  onNodeClick,
  selectedNodeId,
  fitSignal,
}) {
  const fgRef = useRef();

  useEffect(() => {
    if (fgRef.current) {
      fgRef.current.d3Force("charge").strength(-160);
      fgRef.current.d3Force("link").distance(70);
    }
  }, [graphData]);

  const hasHighlight = highlightNodeIds && highlightNodeIds.size > 0;

  useEffect(() => {
    if (!fgRef.current) return;
    const doFit = () => {
      if (hasHighlight) {
        fgRef.current.zoomToFit(500, 120, (n) => highlightNodeIds.has(n.id));
      } else {
        fgRef.current.zoomToFit(500, 80);
      }
    };
    const t1 = setTimeout(doFit, 400);
    const t2 = setTimeout(doFit, 1200);
    const t3 = setTimeout(doFit, 2200);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitSignal]);

  const nodeCanvasObject = useCallback(
    (node, ctx, globalScale) => {
      const isGhost = node.type === "ghost";
      const dim = hasHighlight && !highlightNodeIds.has(node.id);
      const radius = Math.max(3, Math.sqrt(node.degree || 1) * 2.2);
      const color = TYPE_COLOR[node.type] || "#cbd5e0";

      ctx.save();
      ctx.globalAlpha = dim ? 0.12 : 1;

      if (isGhost) {
        ctx.setLineDash([2, 2]);
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.setLineDash([]);
      } else {
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();
        if (node.id === selectedNodeId) {
          ctx.lineWidth = 2;
          ctx.strokeStyle = "#fff";
          ctx.stroke();
        }
      }

      if (globalScale > 1.2 || node.id === selectedNodeId || (hasHighlight && highlightNodeIds.has(node.id))) {
        const label = node.name || node.id;
        const fontSize = 11 / globalScale;
        ctx.font = `${fontSize}px Inter, sans-serif`;
        ctx.fillStyle = isGhost ? "#a0aec0" : "#e2e8f0";
        ctx.globalAlpha = dim ? 0.15 : 0.95;
        ctx.textAlign = "center";
        ctx.fillText(
          label.length > 28 ? label.slice(0, 26) + "…" : label,
          node.x,
          node.y + radius + fontSize
        );
      }
      ctx.restore();
    },
    [hasHighlight, highlightNodeIds, selectedNodeId]
  );

  const linkColor = useCallback(
    (link) => {
      if (link.type === "CONTRADICTS") return "rgba(252,129,129,0.9)";
      if (!hasHighlight) return "rgba(160,174,192,0.35)";
      const s = link.source.id ?? link.source;
      const t = link.target.id ?? link.target;
      const active = highlightNodeIds.has(s) && highlightNodeIds.has(t);
      return active ? "rgba(246,173,85,0.9)" : "rgba(160,174,192,0.06)";
    },
    [hasHighlight, highlightNodeIds]
  );

  const linkLineDash = useCallback((link) => (link.type === "CONTRADICTS" ? [4, 3] : null), []);
  const linkWidth = useCallback((link) => (link.type === "CONTRADICTS" ? 2.5 : 1), []);

  return (
    <ForceGraph2D
      ref={fgRef}
      graphData={graphData}
      backgroundColor="#0f1420"
      nodeId="id"
      nodeCanvasObject={nodeCanvasObject}
      nodePointerAreaPaint={(node, color, ctx) => {
        const radius = Math.max(4, Math.sqrt(node.degree || 1) * 2.2) + 2;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
        ctx.fill();
      }}
      linkColor={linkColor}
      linkDirectionalParticles={(link) => {
        if (!hasHighlight) return 0;
        const s = link.source.id ?? link.source;
        const t = link.target.id ?? link.target;
        return highlightNodeIds.has(s) && highlightNodeIds.has(t) ? 2 : 0;
      }}
      linkDirectionalParticleWidth={2.2}
      linkDirectionalParticleColor={() => "#f6ad55"}
      linkWidth={linkWidth}
      linkLineDash={linkLineDash}
      onNodeClick={(node) => onNodeClick?.(node)}
      cooldownTicks={100}
    />
  );
}
