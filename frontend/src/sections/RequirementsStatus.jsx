import { motion } from "framer-motion";
import { Check, TriangleAlert, X } from "lucide-react";
import SectionHeading from "../components/ui/SectionHeading";
import Card from "../components/ui/Card";

// Статус выражается формой иконки и насыщенностью, а не семафором
// красный/жёлтый/зелёный — в палитре нет отдельных цветов под это.
const STATUS_STYLE = {
  done: { icon: Check, className: "bg-primary/10 text-primary", label: "Реализовано" },
  partial: { icon: TriangleAlert, className: "bg-secondary/10 text-secondary", label: "Частично" },
  none: { icon: X, className: "bg-ink/10 text-ink/40", label: "Не реализовано" },
};

const ROWS = [
  { status: "done", title: "Онтология домена и граф-хранилище с обходом связей", note: "Serving-слой — Neo4j (реальный Cypher); сборка графа NLP-пайплайном — NetworkX." },
  { status: "done", title: "Многопараметрические запросы", note: "Материал + процесс + условие + география + период, на обоих граф-бэкендах." },
  { status: "done", title: "Числовые диапазоны и ограничения", note: "Разбор ≤ / ≥ / диапазон из текста вопроса, транслируется в Cypher WHERE на Neo4j." },
  { status: "done", title: "Различение RU / зарубежной практики", note: "Атрибут country, детектор в тексте запроса." },
  { status: "done", title: "Модель верификации (источник / достоверность / дата)", note: "Отображается в ответе и в панели деталей; ручной workflow review — не реализован." },
  { status: "done", title: "Версионирование фактов", note: "Новое значение обновляет факт, расхождение сохраняется в истории узла." },
  { status: "done", title: "Визуализация графа, подсветка пробелов", note: "Интерактивный force-граф, тумблер «Показать пробелы в данных»." },
  { status: "done", title: "Подсветка противоречий", note: "CONTRADICTS явные + NEEDS_REVIEW — авто-заподозренные конфликты выводов." },
  { status: "partial", title: "Синтез ответов а-ля литературный обзор", note: "Группировка по источникам есть; авто-выделение консенсус/разногласие — только через противоречия." },
  { status: "done", title: "NLP-пайплайн извлечения сущностей (RU/EN)", note: "Прогнан вживую с YandexGPT Pro на docx/pptx/pdf + OCR." },
  { status: "partial", title: "Дашборды для руководителей", note: "/api/gaps даёт данные для покрытия по темам; специализированный UI-дашборд — в разработке." },
  { status: "partial", title: "Сравнительные таблицы технологий", note: "Видно через ответ на запрос с альтернативами; отдельного UI-виджета таблицы нет." },
  { status: "partial", title: "Мультиязычность (RU / EN)", note: "Словарь синонимов терминов отрасли есть; полноценного перевода запросов/документов нет." },
  { status: "done", title: "RAG-чат по загруженным файлам и ссылкам", note: "PDF/DOCX/TXT и внешние ссылки, хранение в Neo4j (видно на графе), дедупликация по хэшу содержимого, ответ строго по цитатам с указанием страницы/фрагмента и уровнем достоверности." },
  { status: "done", title: "История запросов", note: "Список заданных вопросов, повторное открытие ответа без нового обращения к LLM/эмбеддингам, удаление записи или очистка целиком." },
  { status: "done", title: "Экспорт ответа: PDF / Markdown / JSON", note: "PDF рендерится на бэкенде (кириллица, источники, достоверность), JSON и Markdown — на клиенте из уже полученного ответа. JSON — структурированный, но не JSON-LD (без @context / семантической разметки)." },
  { status: "none", title: "Ролевая модель, разграничение доступа, аудит", note: "Не реализовано в рамках MVP; схема легко расширяется visibility/role." },
  { status: "none", title: "Уведомления о новых публикациях", note: "Не реализовано." },
];

export default function RequirementsStatus() {
  return (
    <section id="status" className="mx-auto max-w-[1600px] px-6 py-20 md:py-28">
      <SectionHeading
        eyebrow="Честная оценка"
        title="Соответствие требованиям ТЗ"
        subtitle="MVP, демонстрирующий архитектуру и ключевую пользовательскую петлю — без преувеличений о том, что ещё не реализовано."
      />

      <div className="mt-12 grid grid-cols-1 gap-3 lg:grid-cols-2">
        {ROWS.map((row, i) => {
          const s = STATUS_STYLE[row.status];
          return (
            <motion.div
              key={row.title}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.4, delay: (i % 8) * 0.05 }}
            >
              <Card className="flex items-start gap-3 p-4">
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${s.className}`}>
                  <s.icon size={14} />
                </span>
                <div className="flex flex-col gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold text-ink">{row.title}</h3>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${s.className}`}>
                      {s.label}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed text-ink/50">{row.note}</p>
                </div>
              </Card>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}
