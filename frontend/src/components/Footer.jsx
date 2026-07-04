import { Share2 } from "lucide-react";

export default function Footer() {
  return (
    <footer>
      <div className="mx-auto flex max-w-[1600px] flex-col gap-6 px-6 py-10 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2 text-ink">
  <span className="flex h-7 w-7 items-center justify-center rounded bg-gradient-to-br from-primary to-accent">
    <Share2 size={14} className="text-bg" />
  </span>

  <div className="flex flex-col leading-tight">
    <span className="text-sm font-bold text-white">
      R&D Knowledge Graph
    </span>
    <span className="text-xs font-medium text-slate-400">
      by Neural Alloy
    </span>
  </div>
</div>

        <span className="text-xs text-ink/50">
          Материалы и горно-металлургические процессы · MVP
        </span>
      </div>
    </footer>
  );
}
