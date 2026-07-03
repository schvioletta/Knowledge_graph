import { useMemo } from "react";
import SectionHeading from "../components/ui/SectionHeading";
import Card from "../components/ui/Card";
import { TYPE_COLOR, TYPE_LABEL, PALETTE } from "../constants";

const SIZE = 420;
const CENTER = SIZE / 2;
const RADIUS = 150;
const RINGS = 4;

function RadarChart({ metrics }) {
  const n = metrics.length;
  if (n === 0) return null;
  const maxValue = Math.max(1, ...metrics.map((m) => m.value));

  const pointAt = (i, ratio) => {
    const angle = -Math.PI / 2 + i * ((2 * Math.PI) / n);
    return [CENTER + ratio * RADIUS * Math.cos(angle), CENTER + ratio * RADIUS * Math.sin(angle)];
  };

  const dataPoints = metrics.map((m, i) => pointAt(i, m.value / maxValue));
  const dataPath = dataPoints.map((p) => p.join(",")).join(" ");

  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full max-w-md">
      {Array.from({ length: RINGS }).map((_, ring) => {
        const ratio = (ring + 1) / RINGS;
        const points = metrics.map((_, i) => pointAt(i, ratio).join(",")).join(" ");
        return (
          <polygon
            key={ring}
            points={points}
            fill="none"
            stroke={PALETTE.ink}
            strokeOpacity="0.12"
            strokeWidth="1"
          />
        );
      })}

      {metrics.map((_, i) => {
        const [x, y] = pointAt(i, 1);
        return (
          <line key={i} x1={CENTER} y1={CENTER} x2={x} y2={y} stroke={PALETTE.ink} strokeOpacity="0.12" />
        );
      })}

      <polygon
        points={dataPath}
        fill={PALETTE.primary}
        fillOpacity="0.15"
        stroke={PALETTE.primary}
        strokeWidth="2"
      />

      {dataPoints.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="3.5" fill={metrics[i].color} />
      ))}

      {metrics.map((m, i) => {
        const [x, y] = pointAt(i, 1.28);
        return (
          <text
            key={m.label}
            x={x}
            y={y}
            fill={PALETTE.ink}
            fillOpacity="0.6"
            fontSize="11"
            textAnchor="middle"
            dominantBaseline="middle"
          >
            {m.label} ({m.value})
          </text>
        );
      })}
    </svg>
  );
}

export default function Coverage({ nodesMap }) {
  const metrics = useMemo(() => {
    const counts = {};
    for (const node of Object.values(nodesMap)) {
      if (node.type === "ghost") continue;
      counts[node.type] = (counts[node.type] || 0) + 1;
    }
    return Object.entries(TYPE_LABEL)
      .filter(([type]) => type !== "ghost")
      .map(([type, label]) => ({ label, value: counts[type] || 0, color: TYPE_COLOR[type] }));
  }, [nodesMap]);

  const total = metrics.reduce((sum, m) => sum + m.value, 0);

  return (
    <section id="coverage" className="mx-auto max-w-[1600px] px-6 py-20 md:py-28">
      <SectionHeading
        eyebrow="Покрытие графа"
        title="Сколько знаний уже связано"
        subtitle="Живой срез загруженного графа — количество узлов на тип сущности, без синтетических данных."
      />

      <Card className="mt-12 flex flex-col items-center gap-8 p-8 lg:flex-row lg:items-center lg:justify-around">
        <RadarChart metrics={metrics} />
        <div className="flex flex-col gap-2">
          <div className="text-4xl font-bold text-ink">{total}</div>
          <div className="text-sm text-ink/50">узлов в текущем графе</div>
          <ul className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs text-ink/60">
            {metrics.map((m) => (
              <li key={m.label} className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ background: m.color }} />
                {m.label}: <b className="text-ink">{m.value}</b>
              </li>
            ))}
          </ul>
        </div>
      </Card>
    </section>
  );
}
