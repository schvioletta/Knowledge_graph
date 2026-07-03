import { motion } from "framer-motion";
import {
  SearchCode,
  GitCompareArrows,
  Grid3x3,
  History,
  Database,
  Languages,
  FileScan,
  Gauge,
} from "lucide-react";
import SectionHeading from "../components/ui/SectionHeading";
import Card from "../components/ui/Card";

const TONES = [
  { bg: "bg-primary/10", text: "text-primary" },
  { bg: "bg-secondary/10", text: "text-secondary" },
  { bg: "bg-accent/10", text: "text-accent" },
  { bg: "bg-ink/10", text: "text-ink" },
];

const CAPABILITIES = [
  {
    icon: SearchCode,
    title: "Гибридный поиск",
    text: "Материал + процесс + условие + география + период, с числовыми диапазонами («сульфаты ≤300 мг/л»), в одном запросе.",
    span: "lg:col-span-2",
  },
  {
    icon: GitCompareArrows,
    title: "Обнаружение противоречий",
    text: "Явные CONTRADICTS и авто-заподозренные NEEDS_REVIEW между выводами по одной связке материал+процесс.",
  },
  {
    icon: Grid3x3,
    title: "Анализ пробелов",
    text: "Матрица покрытия материал × условие/процесс/оборудование — какие комбинации ещё не изучены.",
  },
  {
    icon: History,
    title: "Версионирование фактов",
    text: "Новое значение атрибута обновляет факт, расхождение сохраняется в истории узла с источником и датой.",
  },
  {
    icon: Database,
    title: "Два бэкенда графа",
    text: "NetworkX для сборки NLP-пайплайном, Neo4j (реальный Cypher) для serving — переключается переменной окружения.",
    span: "lg:col-span-2",
  },
  {
    icon: Languages,
    title: "RU / EN домен",
    text: "Словарь синонимов терминов отрасли (electrowinning / электроэкстракция) и морфология падежных окончаний.",
  },
  {
    icon: FileScan,
    title: "NLP из сырых файлов",
    text: "docx / pptx / pdf, включая OCR сканов, чанкинг по языку абзаца, entity resolution по алиасам.",
  },
  {
    icon: Gauge,
    title: "Экономный режим",
    text: "Секции документа вместо целого текста и манифест обработанных файлов — на 5 файлах 13 вызовов LLM вместо 322.",
  },
];

export default function Capabilities() {
  return (
    <section id="capabilities" className="mx-auto max-w-[1600px] px-6 py-20 md:py-28">
      <SectionHeading
        eyebrow="Возможности"
        title="Что уже реализовано"
        subtitle="Только реальные, работающие функции — без обещаний того, чего ещё нет в коде."
      />

      <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {CAPABILITIES.map((c, i) => (
          <motion.div
            key={c.title}
            className={c.span}
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5, delay: i * 0.06 }}
          >
            <Card className="flex h-full flex-col gap-3 p-5">
              <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${TONES[i % TONES.length].bg} ${TONES[i % TONES.length].text}`}>
                <c.icon size={18} />
              </span>
              <h3 className="text-sm font-semibold text-ink">{c.title}</h3>
              <p className="text-sm leading-relaxed text-ink/60">{c.text}</p>
            </Card>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
