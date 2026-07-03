import { Share2 } from "lucide-react";

export default function Footer() {
  return (
    <footer className="bg-bg">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-6 px-6 py-10 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2 text-ink">
          <span className="flex h-7 w-7 items-center justify-center rounded bg-gradient-to-br from-primary to-accent">
            <Share2 size={14} className="text-bg" />
          </span>
          <span className="text-sm font-semibold">R&D Knowledge Graph</span>
        </div>

        <nav className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-ink/70">
          <a href="https://github.com" target="_blank" rel="noreferrer" className="transition hover:text-ink">
            GitHub
          </a>
          <a href="#status" className="transition hover:text-ink">
            API
          </a>
          <a href="#architecture" className="transition hover:text-ink">
            Документация
          </a>
          <a href="#top" className="transition hover:text-ink">
            Контакты
          </a>
        </nav>

        <span className="text-xs text-ink/50">
          Материалы и горно-металлургические процессы · MVP
        </span>
      </div>
    </footer>
  );
}
