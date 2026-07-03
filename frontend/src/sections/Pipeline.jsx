import { motion } from "framer-motion";
import { FileText, Layers, Cpu, GitMerge, ShieldCheck, Share2, SearchCheck } from "lucide-react";
import SectionHeading from "../components/ui/SectionHeading";
import Card from "../components/ui/Card";

const STEPS = [
  { icon: FileText, title: "Документы", text: "docx / pptx / pdf + OCR сканов" },
  { icon: Layers, title: "Ingest & Chunking", text: "язык и смысловые блоки по абзацу" },
  { icon: Cpu, title: "NER-экстракция", text: "LLM по схеме онтологии (schema.py)" },
  { icon: GitMerge, title: "Entity Resolution", text: "алиасы, RU/EN морфология" },
  { icon: ShieldCheck, title: "Валидация", text: "допустимость связей, confidence" },
  { icon: Share2, title: "Knowledge Graph", text: "NetworkX build / Neo4j serving" },
  { icon: SearchCheck, title: "Hybrid Search", text: "граф + числовые фильтры + LLM" },
];

export default function Pipeline() {
  return (
    <section id="pipeline" className="mx-auto max-w-[1600px] px-6 py-20 md:py-28">
      <SectionHeading
        eyebrow="Как это работает"
        title="От сырого документа до подсвеченного ответа"
        subtitle="Реальный пайплайн backend/nlp_pipeline — не демонстрационная схема."
      />

      <div className="relative mt-16 flex flex-col gap-6 lg:flex-row lg:items-stretch lg:gap-3">
        {STEPS.map((s, i) => (
          <div key={s.title} className="relative flex flex-1 items-center">
            <motion.div
              className="w-full"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.5, delay: i * 0.08 }}
            >
              <Card className="flex h-full flex-col items-center gap-2 p-4 text-center">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <s.icon size={18} />
                </span>
                <h3 className="text-sm font-semibold text-ink">{s.title}</h3>
                <p className="text-xs leading-relaxed text-ink/50">{s.text}</p>
              </Card>
            </motion.div>

            {i < STEPS.length - 1 && (
              <svg
                className="absolute top-1/2 left-full z-10 hidden h-6 w-6 -translate-y-1/2 lg:block"
                viewBox="0 0 24 24"
              >
                <line
                  x1="0"
                  y1="12"
                  x2="24"
                  y2="12"
                  stroke="#00b4ff"
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
