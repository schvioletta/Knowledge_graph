const AXES = [
  { value: "material", label: "Материал" },
  { value: "process", label: "Процесс" },
  { value: "condition", label: "Условие" },
  { value: "property", label: "Свойство" },
  { value: "equipment", label: "Оборудование" },
  { value: "facility", label: "Предприятие" },
];

export default function GapToggle({ enabled, onToggle, xAxis, yAxis, onAxisChange, gapCount }) {
  return (
    <div className="flex flex-col gap-2">
      <label className="flex cursor-pointer items-center gap-2 text-sm text-ink/80">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="h-3.5 w-3.5 accent-primary"
        />
        Показать пробелы в данных
      </label>
      {enabled && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <select
            value={xAxis}
            onChange={(e) => onAxisChange(e.target.value, yAxis)}
            className="rounded border border-ink/20 bg-surface px-1.5 py-1 text-ink"
          >
            {AXES.map((a) => (
              <option key={a.value} value={a.value}>{a.label}</option>
            ))}
          </select>
          <span className="text-ink/50">×</span>
          <select
            value={yAxis}
            onChange={(e) => onAxisChange(xAxis, e.target.value)}
            className="rounded border border-ink/20 bg-surface px-1.5 py-1 text-ink"
          >
            {AXES.map((a) => (
              <option key={a.value} value={a.value}>{a.label}</option>
            ))}
          </select>
          <span className="w-full text-secondary">{gapCount} непротестированных комбинаций</span>
        </div>
      )}
    </div>
  );
}
