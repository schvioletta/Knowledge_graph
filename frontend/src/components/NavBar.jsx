import { Share2 } from "lucide-react";

const LINKS = [
  { href: "#architecture", label: "Архитектура" },
  { href: "#status", label: "Возможности" },
];

export default function NavBar() {
  return (
    <header className="sticky top-0 z-50 bg-bg [transform:translateZ(0)] [will-change:transform]">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-6 py-3">
        <a href="#top" className="flex items-center gap-2 text-ink">
  <span className="flex h-8 w-8 items-center justify-center rounded bg-gradient-to-br from-primary to-accent">
    <Share2 size={16} className="text-bg" />
  </span>

  <div className="flex flex-col leading-tight">
    <span className="text-sm font-bold tracking-wide text-white">
      R&D Knowledge Graph
    </span>
    <span className="text-xs font-medium text-slate-400">
      by Neural Alloy
    </span>
  </div>
</a>

        <nav className="hidden items-center gap-6 md:flex">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="text-sm text-ink/70 transition hover:text-ink"
            >
              {l.label}
            </a>
          ))}
        </nav>
      </div>
    </header>
  );
}
