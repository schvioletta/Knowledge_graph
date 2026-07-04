import { motion } from "framer-motion";
import { FolderInput, Cpu, Share2, SearchCode, Telescope, Server, MonitorSmartphone, UserRound } from "lucide-react";
import SectionHeading from "../components/ui/SectionHeading";
import Card from "../components/ui/Card";

const NODES = [
  { icon: FolderInput, title: "Источники", text: "docx / pptx / pdf" },
  { icon: Cpu, title: "NLP-пайплайн", text: "ingest → chunk → NER → resolve → validate" },
  { icon: Share2, title: "Graph Store", text: "NetworkX (build) / Neo4j (serving)" },
  { icon: SearchCode, title: "Hybrid Retriever", text: "граф + числовые фильтры + LLM" },
  { icon: Telescope, title: "Внешний поиск", text: "Google Scholar / Patents по ключевым словам" },
  { icon: Server, title: "FastAPI", text: "/api/graph, /api/search, /api/gaps" },
  { icon: MonitorSmartphone, title: "React UI", text: "force-граф, поиск, детали" },
  { icon: UserRound, title: "Исследователь", text: "вопрос → ответ → источники" },
];

export default function Architecture() {
  return (
    <section id="architecture" className="mx-auto max-w-[1600px] px-6 py-20 md:py-28">
      <SectionHeading
        eyebrow="Архитектура"
        title="Как устроена платформа"
        subtitle="Реальная схема репозитория: сборка графа (NLP) и его обслуживание (поиск/визуализация) разделены сознательно."
      />

      <div className="relative mt-16 flex flex-col gap-4 lg:flex-row lg:items-stretch">
        {NODES.map((n, i) => (
          <div key={n.title} className="relative flex flex-1 items-center">
            <motion.div
              className="w-full"
              initial={{ opacity: 0, scale: 0.94 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.45, delay: i * 0.07 }}
            >
              <Card className="flex h-full flex-col items-center gap-2 p-4 text-center">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-accent/10 text-accent">
                  <n.icon size={18} />
                </span>
                <h3 className="text-sm font-semibold text-ink">{n.title}</h3>
                <p className="text-xs leading-relaxed text-ink/50">{n.text}</p>
              </Card>
            </motion.div>

            {i < NODES.length - 1 && (
              <svg
                className="absolute top-1/2 left-full z-10 hidden h-6 w-8 -translate-y-1/2 lg:block"
                viewBox="0 0 32 24"
              >
                <line
                  x1="0"
                  y1="12"
                  x2="32"
                  y2="12"
                  stroke="#9b7bff"
                  strokeOpacity="0.5"
                  strokeWidth="2"
                  className="animate-flow-dash"
                />
              </svg>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
