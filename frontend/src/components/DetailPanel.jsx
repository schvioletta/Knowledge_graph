import { X } from "lucide-react";
import { TYPE_COLOR, TYPE_LABEL } from "../constants";

const RELATION_LABEL = {
  USES_MATERIAL: "Материал",
  USES_PROCESS: "Процесс",
  AT_CONDITION: "Условие",
  AT_FACILITY: "Предприятие",
  ON_EQUIPMENT: "Оборудование",
  MEASURES_PROPERTY: "Измеряемые свойства",
  PRODUCES_CONCLUSION: "Выводы",
  CONDUCTED_BY: "Команда",
  "incoming::DESCRIBES_EXPERIMENT": "Описан в публикации",
  "incoming::PRODUCES_CONCLUSION": "Вывод получен в эксперименте",
  TAGGED_AS: "Темы",
  AUTHORED_BY: "Авторы",
  VALIDATED_BY: "Подтверждено источником",
  CONTRADICTS: "⚠ Противоречит",
  "incoming::CONTRADICTS": "⚠ Противоречит",
  NEEDS_REVIEW: "🟡 Похоже на конфликт вывода (требует проверки эксперта)",
  "incoming::NEEDS_REVIEW": "🟡 Похоже на конфликт вывода (требует проверки эксперта)",
};

const NUMERIC_LABELS = {
  sulfate_mg_l: "Сульфаты, мг/л",
  chloride_mg_l: "Хлориды, мг/л",
  calcium_mg_l: "Ca, мг/л",
  magnesium_mg_l: "Mg, мг/л",
  sodium_mg_l: "Na, мг/л",
  dry_residue_mg_l: "Сухой остаток, мг/дм³",
  catholyte_flow_rate_m3_h: "Скорость циркуляции католита, м³/ч",
  current_density_a_m2: "Плотность тока, А/м²",
  au_distribution_pct: "Распределение Au, %",
  ag_distribution_pct: "Распределение Ag, %",
  pgm_distribution_pct: "Распределение МПГ, %",
  extraction_rate_pct: "Степень извлечения, %",
  capex_musd: "CAPEX, млн $",
  opex_musd_year: "OPEX, млн $/год",
  capacity_m3_day: "Производительность, м³/сут",
  injection_depth_m: "Глубина закачки, м",
  leach_days: "Срок выщелачивания, сут",
};

function Badge({ children, className = "" }) {
  return (
    <span className={`rounded-full border border-ink/20 bg-surface px-2 py-0.5 text-[11px] text-ink/70 ${className}`}>
      {children}
    </span>
  );
}

export default function DetailPanel({ node, detail, onExpand, onClose }) {
  if (!node) {
    return (
      <div className="flex h-full items-center p-5 text-sm text-ink/50">
        Выберите узел на графе, чтобы увидеть детали и связи.
      </div>
    );
  }

  const attrs = node.attrs || {};
  const numericEntries = Object.entries(attrs).filter(([k]) => NUMERIC_LABELS[k]);

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-4">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: TYPE_COLOR[node.type] }} />
        <span className="flex-1 text-[11px] font-semibold uppercase tracking-wide text-ink/50">
          {TYPE_LABEL[node.type] || node.type}
        </span>
        <button onClick={onClose} className="text-ink/50 transition hover:text-ink">
          <X size={16} />
        </button>
      </div>

      <h3 className="text-base font-semibold text-ink">{node.name}</h3>

      <div className="flex flex-wrap gap-1.5">
        {attrs.date && <Badge>📅 {attrs.date}</Badge>}
        {attrs.country && (
          <Badge className={attrs.country === "RU" ? "border-primary/40 text-primary" : "border-accent/40 text-accent"}>
            {attrs.country === "RU" ? "РФ" : "Мир"}
          </Badge>
        )}
        {attrs.confidence && <Badge>достоверность: {attrs.confidence}</Badge>}
      </div>

      {attrs.effect && <div className="text-sm font-medium text-secondary">Эффект: {attrs.effect}</div>}

      {numericEntries.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="text-[11px] uppercase tracking-wide text-ink/50">Числовые параметры</div>
          <ul className="flex flex-col text-xs">
            {numericEntries.map(([k, v]) => (
              <li key={k} className="flex justify-between border-b border-dashed border-ink/15 py-1">
                <span className="text-ink/60">{NUMERIC_LABELS[k]}</span>
                <b className="text-ink">{v}</b>
              </li>
            ))}
          </ul>
        </div>
      )}

      {Array.isArray(attrs._history) && attrs._history.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="text-[11px] uppercase tracking-wide text-ink/50">История изменений факта</div>
          <ul className="flex flex-col gap-2 text-xs">
            {attrs._history.map((h, i) => (
              <li key={i} className="border-b border-dashed border-ink/15 pb-2">
                {NUMERIC_LABELS[h.attr] || h.attr}: {String(h.old_value)} →{" "}
                <b className="text-ink">{String(h.new_value)}</b>
                <br />
                <span className="text-[10px] text-ink/40">{h.source_file}, {h.changed_at}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {detail &&
        Object.entries(RELATION_LABEL).map(([key, label]) => {
          const items = detail[key];
          if (!items || items.length === 0) return null;
          return (
            <div key={key} className="flex flex-col gap-1">
              <div className="text-[11px] uppercase tracking-wide text-ink/50">{label}</div>
              <ul className="list-disc pl-4 text-sm text-ink/80">
                {items.map((it) => (
                  <li key={it.id}>{it.name}</li>
                ))}
              </ul>
            </div>
          );
        })}

      <button
        onClick={() => onExpand(node.id)}
        className="mt-2 rounded border border-ink/20 bg-surface py-2 text-sm text-ink transition hover:border-primary/50"
      >
        Развернуть соседей ↴
      </button>
    </div>
  );
}
