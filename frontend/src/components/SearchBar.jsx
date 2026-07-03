import { useState } from "react";
import { Search } from "lucide-react";
import { EXAMPLE_QUERIES } from "../constants";

export default function SearchBar({ onSearch, loading }) {
  const [value, setValue] = useState("");

  const submit = (e) => {
    e.preventDefault();
    if (value.trim()) onSearch(value.trim());
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <div className="flex items-center gap-2 rounded-md border border-ink/20 bg-surface-deep px-3 py-2 focus-within:border-primary">
        <Search size={16} className="shrink-0 text-ink/50" />
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Что известно по материалу X при процессе Y и условии Z? Какой эффект на свойство W?"
          className="min-w-0 flex-1 bg-transparent text-sm text-ink placeholder:text-ink/40 focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading}
          className="shrink-0 rounded bg-primary px-4 py-1.5 text-sm font-semibold text-bg transition hover:brightness-110 disabled:opacity-60"
        >
          {loading ? "Поиск…" : "Спросить"}
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {EXAMPLE_QUERIES.map((ex) => (
          <button
            type="button"
            key={ex}
            onClick={() => {
              setValue(ex);
              onSearch(ex);
            }}
            className="rounded-full border border-ink/20 bg-surface-deep px-2.5 py-1 text-xs text-ink/60 transition hover:border-primary/50 hover:text-ink"
          >
            {ex}
          </button>
        ))}
      </div>
    </form>
  );
}
