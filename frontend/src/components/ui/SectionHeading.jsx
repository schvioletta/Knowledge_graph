import { motion } from "framer-motion";

export default function SectionHeading({ eyebrow, title, subtitle, align = "left" }) {
  const alignClass = align === "center" ? "items-center text-center mx-auto" : "items-start text-left";

  return (
    <motion.div
      className={`flex flex-col gap-4 max-w-3xl ${alignClass}`}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.6, ease: "easeOut" }}
    >
      {eyebrow && (
        <span className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
          {eyebrow}
        </span>
      )}
      <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold leading-tight text-ink">
        {title}
      </h2>
      {subtitle && <p className="text-base md:text-lg text-ink/60 leading-relaxed">{subtitle}</p>}
    </motion.div>
  );
}
