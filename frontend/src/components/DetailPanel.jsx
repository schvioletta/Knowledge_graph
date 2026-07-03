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

export default function DetailPanel({ node, detail, onExpand, onClose }) {
  if (!node) {
    return (
      <div className="detail-panel empty">
        <p>Выберите узел на графе, чтобы увидеть детали, или задайте вопрос выше.</p>
      </div>
    );
  }

  const attrs = node.attrs || {};
  const numericEntries = Object.entries(attrs).filter(([k]) => NUMERIC_LABELS[k]);

  return (
    <div className="detail-panel">
      <div className="detail-header">
        <span className="type-dot" style={{ background: TYPE_COLOR[node.type] }} />
        <span className="type-label">{TYPE_LABEL[node.type] || node.type}</span>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>
      <h3>{node.name}</h3>
      <div className="meta-row">
        {attrs.date && <span className="badge">📅 {attrs.date}</span>}
        {attrs.country && <span className={`badge country-${attrs.country}`}>{attrs.country === "RU" ? "🇷🇺 РФ" : "🌍 Мир"}</span>}
        {attrs.confidence && <span className="badge">достоверность: {attrs.confidence}</span>}
      </div>
      {attrs.effect && <div className="meta effect">Эффект: {attrs.effect}</div>}

      {numericEntries.length > 0 && (
        <div className="relation-block">
          <div className="relation-label">Числовые параметры</div>
          <ul className="numeric-list">
            {numericEntries.map(([k, v]) => (
              <li key={k}>{NUMERIC_LABELS[k]}: <b>{v}</b></li>
            ))}
          </ul>
        </div>
      )}

      {Array.isArray(attrs._history) && attrs._history.length > 0 && (
        <div className="relation-block">
          <div className="relation-label">🕘 История изменений факта</div>
          <ul className="history-list">
            {attrs._history.map((h, i) => (
              <li key={i}>
                {NUMERIC_LABELS[h.attr] || h.attr}: {String(h.old_value)} → <b>{String(h.new_value)}</b>
                <br />
                <span className="history-meta">{h.source_file}, {h.changed_at}</span>
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
            <div className="relation-block" key={key}>
              <div className="relation-label">{label}</div>
              <ul>
                {items.map((it) => (
                  <li key={it.id}>{it.name}</li>
                ))}
              </ul>
            </div>
          );
        })}

      <button className="expand-btn" onClick={() => onExpand(node.id)}>
        Развернуть соседей ↴
      </button>
    </div>
  );
}
