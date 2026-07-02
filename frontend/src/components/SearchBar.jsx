import { useState } from "react";

const EXAMPLES = [
  "Какие методы обессоливания воды подходят при сульфатах, хлоридах, Ca, Mg, Na по 200-300 мг/л и сухом остатке не более 1000 мг/дм3?",
  "Какие решения циркуляции католита при электроэкстракции никеля описаны в мировой практике, и какая скорость потока оптимальна?",
  "Распределение Au, Ag и МПГ между медным/никелевым штейном и шлаком за последние 5 лет",
  "Какие способы закачки шахтных вод в глубокие горизонты применялись в России и за рубежом?",
  "Кучное выщелачивание никелевой руды в холодном климате",
];

export default function SearchBar({ onSearch, loading }) {
  const [value, setValue] = useState("");

  const submit = (e) => {
    e.preventDefault();
    if (value.trim()) onSearch(value.trim());
  };

  return (
    <form className="search-bar" onSubmit={submit}>
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Что известно по материалу X при процессе Y и условии Z? Какой эффект на свойство W?"
      />
      <button type="submit" disabled={loading}>
        {loading ? "Поиск…" : "Спросить"}
      </button>
      <div className="examples">
        {EXAMPLES.map((ex) => (
          <button
            type="button"
            key={ex}
            className="example-chip"
            onClick={() => {
              setValue(ex);
              onSearch(ex);
            }}
          >
            {ex}
          </button>
        ))}
      </div>
    </form>
  );
}
