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
    <div className="gap-toggle">
      <label className="switch-label">
        <input type="checkbox" checked={enabled} onChange={(e) => onToggle(e.target.checked)} />
        Показать пробелы в данных
      </label>
      {enabled && (
        <div className="gap-axes">
          <select value={xAxis} onChange={(e) => onAxisChange(e.target.value, yAxis)}>
            {AXES.map((a) => (
              <option key={a.value} value={a.value}>{a.label}</option>
            ))}
          </select>
          <span>×</span>
          <select value={yAxis} onChange={(e) => onAxisChange(xAxis, e.target.value)}>
            {AXES.map((a) => (
              <option key={a.value} value={a.value}>{a.label}</option>
            ))}
          </select>
          <span className="gap-count">{gapCount} непротестированных комбинаций</span>
        </div>
      )}
    </div>
  );
}
