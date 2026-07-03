import { useCallback, useEffect, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { TYPE_COLOR, TYPE_SHAPE, PALETTE } from "../constants";

function roundedRectPath(ctx, x, y, w, h, radius) {
  const r = Math.min(radius, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

function traceShapePath(ctx, shape, x, y, r) {
  switch (shape) {
    case "square": {
      const side = r * 1.6;
      roundedRectPath(ctx, x - side / 2, y - side / 2, side, side, 2);
      break;
    }
    case "rect": {
      const w = r * 2.3;
      const h = r * 1.35;
      roundedRectPath(ctx, x - w / 2, y - h / 2, w, h, 2);
      break;
    }
    case "roundedRect": {
      const w = r * 2.5;
      const h = r * 1.7;
      roundedRectPath(ctx, x - w / 2, y - h / 2, w, h, Math.max(2, r * 0.55));
      break;
    }
    case "diamond": {
      ctx.beginPath();
      ctx.moveTo(x, y - r * 1.2);
      ctx.lineTo(x + r * 1.2, y);
      ctx.lineTo(x, y + r * 1.2);
      ctx.lineTo(x - r * 1.2, y);
      ctx.closePath();
      break;
    }
    case "triangle": {
      ctx.beginPath();
      ctx.moveTo(x, y - r * 1.25);
      ctx.lineTo(x + r * 1.1, y + r * 0.8);
      ctx.lineTo(x - r * 1.1, y + r * 0.8);
      ctx.closePath();
      break;
    }
    case "hexagon": {
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i - Math.PI / 2;
        const px = x + r * 1.15 * Math.cos(angle);
        const py = y + r * 1.15 * Math.sin(angle);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      break;
    }
    case "circle":
    default:
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      break;
  }
}

export default function GraphView({
  graphData,
  highlightNodeIds,
  onNodeClick,
  selectedNodeId,
  fitSignal,
}) {
  const fgRef = useRef();
  const wrapperRef = useRef();
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [hoveredNodeId, setHoveredNodeId] = useState(null);

  // react-force-graph-2d only measures its container once on mount; in dev mode
  // Tailwind's stylesheet can land a tick after that first measurement, freezing
  // the canvas at a near-zero size. Track the container ourselves and pass
  // explicit width/height instead of relying on its own auto-detection.
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setSize({ width, height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

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
      // Радиус и толщина линий держат минимум в экранных пикселях (/globalScale),
      // иначе на большом графе после zoomToFit узлы схлопываются в невидимые
      // доли пикселя — это ухудшает читаемость, а не про запрещённый glow.
      const minScreenRadius = 2.6 / globalScale;
      const radius = Math.max(minScreenRadius, Math.sqrt(node.degree || 1) * 2.2);
      const color = TYPE_COLOR[node.type] || PALETTE.ink;
      const { shape, filled } = TYPE_SHAPE[node.type] || { shape: "circle", filled: true };
      const isHovered = node.id === hoveredNodeId;
      const isActive = node.id === selectedNodeId || isHovered || (hasHighlight && highlightNodeIds.has(node.id));

      ctx.save();
      ctx.globalAlpha = dim ? 0.15 : 1;

      if (isGhost) {
        ctx.globalAlpha = dim ? 0.15 : 0.55;
        ctx.setLineDash([2, 2]);
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5 / globalScale;
        traceShapePath(ctx, shape, node.x, node.y, radius);
        ctx.stroke();
        ctx.setLineDash([]);
      } else {
        traceShapePath(ctx, shape, node.x, node.y, radius);
        if (filled) {
          ctx.fillStyle = color;
          ctx.fill();
        } else {
          ctx.lineWidth = 2 / globalScale;
          ctx.strokeStyle = color;
          ctx.stroke();
        }

        if (isActive) {
          traceShapePath(ctx, shape, node.x, node.y, radius + 2);
          ctx.lineWidth = 2.2 / globalScale;
          ctx.strokeStyle = isHovered ? PALETTE.secondary : PALETTE.primary;
          ctx.stroke();
        }
      }

      if (globalScale > 1.2 || node.id === selectedNodeId || isHovered || (hasHighlight && highlightNodeIds.has(node.id))) {
        const label = node.name || node.id;
        const fontSize = 11 / globalScale;
        ctx.font = `${fontSize}px Inter, sans-serif`;
        ctx.fillStyle = PALETTE.ink;
        ctx.globalAlpha = dim ? 0.2 : isGhost ? 0.6 : 0.9;
        ctx.textAlign = "center";
        ctx.fillText(
          label.length > 28 ? label.slice(0, 26) + "…" : label,
          node.x,
          node.y + radius + fontSize
        );
      }
      ctx.restore();
    },
    [hasHighlight, highlightNodeIds, selectedNodeId, hoveredNodeId]
  );

  const linkEndpoints = useCallback((link) => ({
    s: link.source?.id ?? link.source,
    t: link.target?.id ?? link.target,
  }), []);

  const isPathLink = useCallback(
    (link) => {
      if (!hasHighlight) return false;
      const { s, t } = linkEndpoints(link);
      return highlightNodeIds.has(s) && highlightNodeIds.has(t);
    },
    [hasHighlight, highlightNodeIds, linkEndpoints]
  );

  const isHoverLink = useCallback(
    (link) => {
      if (!hoveredNodeId) return false;
      const { s, t } = linkEndpoints(link);
      return s === hoveredNodeId || t === hoveredNodeId;
    },
    [hoveredNodeId, linkEndpoints]
  );

  // Рёбра CONTRADICTS/NEEDS_REVIEW всегда остаются на переднем плане (не гаснут
  // при поиске/наведении на другой узел) — это сигналы, которые нельзя пропустить.
  const isSpecialLink = (link) => link.type === "CONTRADICTS" || link.type === "NEEDS_REVIEW";
  const isActiveLink = useCallback(
    (link) => isPathLink(link) || isHoverLink(link) || isSpecialLink(link),
    [isPathLink, isHoverLink]
  );

  const linkColor = useCallback(
    (link) => {
      if (isHoverLink(link) || isPathLink(link)) return PALETTE.primary;
      if (link.type === "CONTRADICTS") return `color-mix(in srgb, ${PALETTE.ink} 92%, transparent)`;
      if (link.type === "NEEDS_REVIEW") return `color-mix(in srgb, ${PALETTE.ink} 72%, transparent)`;
      if (hasHighlight) return `color-mix(in srgb, ${PALETTE.ink} 8%, transparent)`;
      if (hoveredNodeId) return `color-mix(in srgb, ${PALETTE.ink} 12%, transparent)`;
      // Базовая видимость связей поднята с 28% до 45% — структура графа должна
      // читаться и без наведения/поиска, а не только в подсвеченном состоянии.
      return `color-mix(in srgb, ${PALETTE.ink} 45%, transparent)`;
    },
    [isHoverLink, isPathLink, hasHighlight, hoveredNodeId]
  );

  const linkLineDash = useCallback((link) => {
    if (link.type === "CONTRADICTS") return [5, 3];
    if (link.type === "NEEDS_REVIEW") return [1, 3];
    return null;
  }, []);

  const linkWidth = useCallback(
    (link) => {
      if (isHoverLink(link) || isPathLink(link)) return 2.6;
      if (link.type === "CONTRADICTS") return 2.6;
      if (link.type === "NEEDS_REVIEW") return 2;
      return 1.3;
    },
    [isHoverLink, isPathLink]
  );

  const linkCanvasObjectMode = useCallback((link) => (isActiveLink(link) ? "before" : undefined), [isActiveLink]);

  // Glow рисуется только для «активных» связей (путь ответа/наведённый узел/
  // CONTRADICTS/NEEDS_REVIEW) — их всегда немного, поэтому лишняя draw-call на
  // каждый кадр не бьёт по производительности. Мягкий ореол рисуется ДО
  // стандартной линии (mode="before"), а поверх него библиотека сама рисует
  // чёткую линию через linkColor/linkWidth/linkLineDash — это даёт классический
  // эффект bloom без замены базового рендера.
  const linkCanvasObject = useCallback(
    (link, ctx) => {
      const { source: s, target: t } = link;
      if (typeof s !== "object" || typeof t !== "object" || s.x == null || t.x == null) return;
      const color = linkColor(link);
      ctx.save();
      ctx.globalAlpha = 0.5;
      ctx.strokeStyle = color;
      ctx.lineWidth = linkWidth(link) * 3;
      ctx.shadowColor = color;
      ctx.shadowBlur = 10;
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
      ctx.stroke();
      ctx.restore();
    },
    [linkColor, linkWidth]
  );

  const handleNodeHover = useCallback((node) => {
    setHoveredNodeId(node?.id ?? null);
  }, []);

  return (
    <div
      ref={wrapperRef}
      className="h-full w-full"
      style={{ cursor: hoveredNodeId ? "pointer" : "default", contain: "strict", isolation: "isolate" }}
    >
      <ForceGraph2D
        ref={fgRef}
        width={size.width || undefined}
        height={size.height || undefined}
        graphData={graphData}
        backgroundColor={PALETTE.surface}
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
        linkWidth={linkWidth}
        linkLineDash={linkLineDash}
        linkCanvasObjectMode={linkCanvasObjectMode}
        linkCanvasObject={linkCanvasObject}
        onNodeHover={handleNodeHover}
        onNodeClick={(node) => onNodeClick?.(node)}
        cooldownTicks={100}
      />
    </div>
  );
}
