// Тёмная палитра проекта (предыдущая цветовая версия) — см. :root в index.css.
export const PALETTE = {
  primary: "#00b4ff",
  secondary: "#4fd1c5",
  accent: "#9b7bff",
  surface: "#0d1522",
  ink: "#e2e8f0",
};

export const TYPE_COLOR = {
  material: PALETTE.primary,
  process: PALETTE.secondary,
  experiment: PALETTE.primary,
  property: PALETTE.secondary,
  condition: PALETTE.accent,
  equipment: PALETTE.accent,
  facility: PALETTE.accent,
  team: PALETTE.secondary,
  expert: PALETTE.ink,
  topic: PALETTE.ink,
  publication: PALETTE.ink,
  conclusion: PALETTE.ink,
  ghost: PALETTE.ink,
};

export const TYPE_LABEL = {
  material: "Материал",
  process: "Процесс",
  experiment: "Эксперимент",
  property: "Свойство",
  condition: "Условие",
  equipment: "Оборудование",
  facility: "Предприятие",
  team: "Лаборатория",
  expert: "Эксперт",
  topic: "Тема",
  publication: "Публикация",
  conclusion: "Вывод",
  ghost: "Пробел",
};

// Геометрия несёт различие между типами вместо цвета — палитра намеренно
// ограничена, поэтому circle/square/rect/diamond/triangle/hexagon и
// filled/outline берут на себя работу, которую в other системах делают цвета.
export const TYPE_SHAPE = {
  material: { shape: "circle", filled: true },
  process: { shape: "square", filled: true },
  experiment: { shape: "diamond", filled: true },
  property: { shape: "triangle", filled: true },
  condition: { shape: "triangle", filled: false },
  equipment: { shape: "rect", filled: true },
  facility: { shape: "rect", filled: false },
  team: { shape: "hexagon", filled: false },
  expert: { shape: "circle", filled: false },
  topic: { shape: "hexagon", filled: true },
  publication: { shape: "roundedRect", filled: false },
  conclusion: { shape: "diamond", filled: false },
  ghost: { shape: "circle", filled: false },
};

export const FILTERABLE_TYPES = Object.keys(TYPE_LABEL).filter((t) => t !== "ghost");

export const EXAMPLE_QUERIES = [
  "Какие методы обессоливания воды подходят при сульфатах, хлоридах, Ca, Mg, Na по 200-300 мг/л и сухом остатке не более 1000 мг/дм3?",
  "Какие решения циркуляции католита при электроэкстракции никеля описаны в мировой практике, и какая скорость потока оптимальна?",
  "Распределение Au, Ag и МПГ между медным/никелевым штейном и шлаком за последние 5 лет",
  "Какие способы закачки шахтных вод в глубокие горизонты применялись в России и за рубежом?",
  "Кучное выщелачивание никелевой руды в холодном климате",
];
