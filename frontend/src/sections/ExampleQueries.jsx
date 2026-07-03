import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import SectionHeading from "../components/ui/SectionHeading";
import Card from "../components/ui/Card";
import { EXAMPLE_QUERIES } from "../constants";

export default function ExampleQueries({ onSelect }) {
  return (
    <section id="examples" className="mx-auto max-w-[1600px] px-6 py-20 md:py-28">
      <SectionHeading
        eyebrow="Демонстрация поиска"
        title="Примеры запросов из ТЗ"
        subtitle="Каждый запрос выполняется прямо по загруженному графу — нажмите, чтобы увидеть подсвеченный путь рассуждения."
      />

      <div className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-2">
        {EXAMPLE_QUERIES.map((q, i) => (
          <motion.button
            key={q}
            onClick={() => onSelect(q)}
            className="text-left"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5, delay: i * 0.06 }}
          >
            <Card className="flex h-full items-start gap-3 p-5 transition hover:border-primary/40">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <ArrowUpRight size={16} />
              </span>
              <p className="text-sm leading-relaxed text-ink/70">{q}</p>
            </Card>
          </motion.button>
        ))}
      </div>
    </section>
  );
}
