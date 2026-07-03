import { motion } from "framer-motion";
import { Trash2, Copy, Timer, Database, AlertTriangle } from "lucide-react";
import SectionHeading from "../components/ui/SectionHeading";
import Card from "../components/ui/Card";

const TONES = [
  { bg: "bg-primary/10", text: "text-primary" },
  { bg: "bg-secondary/10", text: "text-secondary" },
  { bg: "bg-accent/10", text: "text-accent" },
  { bg: "bg-ink/10", text: "text-ink" },
];

const PROBLEMS = [
  {
    icon: Trash2,
    title: "Потеря знаний",
    text: "Результаты экспериментов и выводы оседают в отчётах на диске и уходят вместе с исследователем — без графа связей их не найти повторно.",
  },
  {
    icon: Copy,
    title: "Дублирование исследований",
    text: "Одна и та же комбинация материал × процесс проверяется заново, потому что никто не видел прошлый отчёт другой лаборатории.",
  },
  {
    icon: Timer,
    title: "Медленный поиск",
    text: "Ответ на вопрос «что уже известно про X при Y и Z» требует вручную перечитать десятки документов вместо одного запроса к графу.",
  },
  {
    icon: Database,
    title: "Разрозненные данные",
    text: "Публикации, эксперименты, материалы, оборудование и эксперты живут в разных файлах и системах, не связанные друг с другом.",
  },
  {
    icon: AlertTriangle,
    title: "Противоречивые выводы",
    text: "Разные источники по одной связке материал+процесс дают разные цифры — без автоматической подсветки конфликт остаётся незамеченным.",
  },
];

export default function ProblemCards() {
  return (
    <section id="problems" className="mx-auto max-w-[1600px] px-6 py-20 md:py-28">
      <SectionHeading
        eyebrow="Проблема"
        title="Знания рассеяны — граф их собирает"
        subtitle="Пять симптомов, знакомых любому R&D-подразделению в горно-металлургической отрасли."
      />

      <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {PROBLEMS.map((p, i) => (
          <motion.div
            key={p.title}
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5, delay: i * 0.08, ease: "easeOut" }}
          >
            <Card className="flex h-full flex-col gap-3 p-5">
              <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${TONES[i % TONES.length].bg} ${TONES[i % TONES.length].text}`}>
                <p.icon size={18} />
              </span>
              <h3 className="text-sm font-semibold text-ink">{p.title}</h3>
              <p className="text-sm leading-relaxed text-ink/60">{p.text}</p>
            </Card>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
