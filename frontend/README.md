# Frontend — R&D Knowledge Graph

React + Vite + `react-force-graph-2d`. Интерактивный force-граф, RAG-чат по
документам и внешним источникам. Полное описание проекта — в корневом
[`README.md`](../README.md) и [`backend/README.md`](../backend/README.md).

## Запуск

```bash
npm install
npm run dev      # http://localhost:5173, API на http://localhost:8000 (VITE_API_BASE)
npm run build
```

## Ключевые части UI

- **`App.jsx`** — оркестрация запроса; после «Спросить» плавный скролл + фокус на
  блоке результатов «По документам».
- **`components/ResultsPanel.jsx`** — ответ RAG, ход рассуждений (Thinking),
  раздел «Источники» тремя категориями: внутренняя база, Google Scholar, Google
  Patents (для внешних — авторы, год, журнал/патент, ссылка, ключевые слова,
  релевантность).
- **`components/GraphView.jsx`** — force-граф; внешние публикации помечены бейджем
  `S`/`P` и цветом контура. Легенда — `components/FilterDock.jsx`, метаданные узла —
  `components/DetailPanel.jsx`.
- **`sections/`** — информационные блоки лендинга (архитектура, возможности,
  пайплайн, статус требований).

---

## React + Vite (шаблон)

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.
