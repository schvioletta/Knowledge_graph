import { Share2, GitBranch } from "lucide-react";

const LINKS = [
  { href: "#workbench", label: "Граф" },
  { href: "#capabilities", label: "Возможности" },
  { href: "#architecture", label: "Архитектура" },
  { href: "#status", label: "Статус ТЗ" },
];

export default function NavBar() {
  return (
    <header className="sticky top-0 z-50 bg-bg">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-6 py-3">
        <a href="#top" className="flex items-center gap-2 text-ink">
          <span className="flex h-8 w-8 items-center justify-center rounded bg-gradient-to-br from-primary to-accent">
            <Share2 size={16} className="text-bg" />
          </span>
          <span className="text-sm font-semibold tracking-wide">
            R&D Knowledge Graph
          </span>
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

        <a
          href="https://github.com"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2 rounded border border-ink/30 px-3 py-1.5 text-sm text-ink/80 transition hover:border-ink/60 hover:text-ink"
        >
          <GitBranch size={15} />
          GitHub
        </a>
      </div>
    </header>
  );
}
