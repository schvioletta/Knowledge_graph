# R&D Knowledge Graph — горно-металлургическая отрасль

Единая карта знаний, связывающая публикации, эксперименты, материалы,
процессы, условия, оборудование, предприятия, лаборатории/экспертов и
выводы, с гибридным (граф + числовые фильтры + LLM) поиском и интерактивной
визуализацией графа в стиле Connected Papers.

Репозиторий также содержит исходный базовый RAG по PDF (`rag_qdrant.py`),
из которого вырос этот проект.

## Важно: доступ к реальным данным и к внешним LLM API из песочницы

Корпус документов на Яндекс.Диске (см. задание) недоступен из среды
выполнения агента — исходящий трафик на `disk.yandex.ru` и
`cloud-api.yandex.net` блокируется политикой песочницы (HTTP 403 на
уровне egress-прокси, не временная ошибка). Датасет в `data/sample_graph.json`
собран вручную по образцу того, что должен извлекать NLP-пайплайн
из реальных отчётов/статей/патентов, и целенаправленно покрывает все 4
примера запросов из ТЗ (обессоливание воды, циркуляция католита при
электроэкстракции никеля, распределение Au/Ag/МПГ между штейном и шлаком,
закачка шахтных вод), включая намеренный пробел в данных и пару
противоречащих друг другу выводов.

NLP-пайплайн (`backend/nlp_pipeline/`) проверен и вживую прогнан с реальным
LLM (YandexGPT Pro, см. «NLP-пайплайн» ниже) на документах из `data/raw/` —
docx/pptx/pdf, включая OCR для сканов, RU и EN в одном документе. Экстракция
даёт связный граф (сущности реально соединены осмысленными связями
`DESCRIBES_EXPERIMENT`/`USES_MATERIAL`/`USES_PROCESS`/`AUTHORED_BY`/`TAGGED_AS`
и т.д., а не только изолированные узлы Publication). `data/smoke_graph.json` —
результат такого прогона на выборке документов; полный `data/real_graph.json`
получается тем же способом на всём корпусе.

## Архитектура

- **Онтология** (`backend/schema.py`) — сущности `Publication, Experiment,
  Material, Process, Property, Condition, Equipment, Facility, Team, Expert,
  Topic, Conclusion` и связи между ними (`USES_MATERIAL, USES_PROCESS,
  AT_CONDITION, AT_FACILITY, ON_EQUIPMENT, MEASURES_PROPERTY,
  PRODUCES_CONCLUSION, DESCRIBES_EXPERIMENT, CONDUCTED_BY, AUTHORED_BY,
  TAGGED_AS, MEMBER_OF, CONTRADICTS, VALIDATED_BY`). Модель верификации
  фактов — атрибуты `source`, `confidence` (высокая/средняя/низкая), `date`,
  `country` (RU/INTL) на узлах Experiment/Publication/Conclusion. Числовые
  параметры процессов (концентрации, скорости, CAPEX/OPEX и т.д.) хранятся
  прямо в атрибутах узла Experiment — это позволяет фильтровать по
  диапазонам без разрастания графа отдельными узлами на каждое число.
- **Граф-стор** (`backend/graph_store.py`) — обёртка над NetworkX (легко
  заменить на Neo4j/Neptune при переходе на реальный масштаб): загрузка/
  сохранение в JSON, обход соседей, структурные запросы вида «эксперименты
  с материалом X при процессе Y и условии Z» (с OR-альтернативами и
  числовыми диапазонами), анализ пробелов (`gap_matrix`) — какие комбинации
  материал×условие/процесс/оборудование ещё не изучались, поиск
  противоречий (`contradictions_for`).
- **Датасет** (`backend/sample_data.py`) → `data/sample_graph.json`.
- **Гибридный ретривер** (`backend/hybrid_retriever.py`):
  - сопоставление сущностей по названию с грубой обработкой русской
    морфологии (падежные окончания) и словарём синонимов RU/EN
    (electrowinning/электроэкстракция, ПВП/печь взвешенной плавки/fluidized
    bed furnace и т.д.);
  - разбор числовых ограничений из вопроса на естественном языке
    («сульфаты ≤300 мг/л», «200–300 мг/л», «не более 1000 мг/дм³»);
  - определение геопризнака (РФ/мировая практика) и временного диапазона
    («за последние 5 лет»);
  - поддержка альтернатив внутри одного запроса («медным/никелевым
    штейном» → ищет оба варианта);
  - структурный запрос к графу + подсветка обнаруженных противоречий в
    выводах;
  - если заданы `YANDEX_API_KEY`/`YANDEX_FOLDER_ID` — финальная стилистическая полировка
    ответа через LLM; без ключа возвращается детерминированный, но
    содержательный ответ с указанием источника и уровня достоверности.
- **NLP-пайплайн** (`backend/nlp_pipeline/`) — сырой документ (docx/pptx/pdf) →
  граф знаний, совместимый с `schema.py`:
  1. `ingest.py` — извлечение текста: PyMuPDF для текстового слоя PDF, OCR-фолбэк
     через `tesseract` (rus+eng) для сканов, `python-docx`/`python-pptx` для
     Word/PowerPoint. Метаданные файла (имя, дата изменения) — заготовка под
     `source`/`date` в модели верификации.
  2. `chunking.py` — язык определяется на уровне абзаца (`langdetect` +
     эвристика по доле кириллицы, если недоступен), а не всего документа —
     важно для русских отчётов с англоязычными аннотациями. Чанки собираются
     по смысловым блокам (абзац/группа/таблица целиком), а не по фиксированному
     числу токенов, чтобы факт «Материал X при Процессе Y дал Z» не рвался
     границей чанка.
  3. `ner_extract.py` — LLM-экстракция: промпт не дублирует онтологию вручную,
     типы сущностей/связей сериализуются прямо из `EntityType`/`RelationType`
     (`schema.py` остаётся источником истины), ответ парсится в pydantic-модели
     — невалидный тип физически не пройдёт парсинг.
  4. `resolve.py` — entity resolution с персистентной таблицей алиасов
     (`data/alias_table.json`): «Электроэкстракция никеля» из одного отчёта и
     «электроэкстракции никеля» из другого не расходятся на два узла (та же
     морфологическая эвристика, что и в поиске — `backend/lexicon.py`).
  5. `validate.py` — SHACL-подобная проверка: допустимость пары
     (source_type, target_type) для каждого типа связи, обязательные поля
     верификации (`source_file`, `confidence`, `date`) на Experiment/
     Publication/Conclusion.
  6. `graph_writer.py` — confidence не «с потолка»: «высокая» = есть явное
     число с единицей измерения И ≥2 независимых источников, «низкая» =
     единичное неявное упоминание, иначе «средняя»; после вставки вывода
     прогоняется `contradictions_for()` по явным `CONTRADICTS`, плюс
     полуавтоматическое сравнение с другими выводами на той же связке
     Материал+Процесс (текстовое сходство без embeddings) — при умеренном
     сходстве помечается `NEEDS_REVIEW`, а не сразу `CONTRADICTS` (ролевой
     модели и ручного review пока нет, поэтому система не берёт на себя
     решение о конфликте, только подсвечивает кандидата).
  7. `sampling.py` + `sections.py` — экономия LLM-вызовов на больших корпусах:
     `sampling.py` отбирает не более N файлов на категорию (категория —
     подпапка внутри `--raw-root`, либо расширение файла как фолбэк),
     стратегией `random`/`largest`/`newest`/`most_tables`, с фиксированным
     `--seed` для воспроизводимости. `sections.py` вместо всего документа
     достаёт только аннотацию/методы/результаты/заключение (по заголовкам
     Word-стиля или эвристике «короткая строка без точки в конце»; если
     формальной структуры нет — берёт начало и конец документа как
     приближение). Это включено по умолчанию (`--full-document` — выключить).
  8. `pipeline.py` — CLI-оркестратор всех этапов.
  9. `eval.py` — считает precision/recall/F1 по сущностям и связям (с fuzzy-
     сопоставлением имён) против ручного golden-набора `data/golden/*.json`
     (формат — см. докстринг `eval.py`); сам набор пока не размечен, каталог
     в репозитории отсутствует — это задел на будущее, а не готовая метрика.
  10. `manifest.py` — манифест обработанных файлов (`data/processed_manifest.json`
      по умолчанию, ключ — sha256 содержимого файла): повторный запуск пайплайна
      на тех же файлах пропускает их без единого LLM-вызова, а изменённый файл
      (другой sha256) обрабатывается заново. `--force` игнорирует манифест.

  ```bash
  export YANDEX_API_KEY=...
  export YANDEX_FOLDER_ID=...   # YANDEX_MODEL по умолчанию "aliceai-llm-flash"

  # экономный режим (по умолчанию): только ключевые секции, опционально выборка по категориям
  python -m backend.nlp_pipeline.pipeline data/raw/**/* --per-category 3 --strategy random --out data/real_graph.json

  # повторный прогон: файлы без изменений пропускаются (data/processed_manifest.json)
  python -m backend.nlp_pipeline.pipeline data/raw/**/* --per-category 3 --strategy random --out data/real_graph.json --force

  # весь корпус целиком, без выборки и без обрезки до секций
  python -m backend.nlp_pipeline.pipeline data/raw/*.docx data/raw/*.pptx data/raw/*.pdf --full-document --out data/real_graph.json

  # смоук-тест: первые 20 файлов — быстро проверить, что пайплайн отрабатывает,
  # прежде чем гонять LLM на всём корпусе
  python -m backend.nlp_pipeline.pipeline data/raw/**/* --limit 20 --out data/smoke_graph.json

  python -m backend.nlp_pipeline.eval data/golden   # precision/recall, если golden-набор размечен (см. eval.py)

  # подставить нужный граф в бэкенд (сначала смоук-граф для проверки, затем боевой real_graph.json)
  GRAPH_DATA_PATH=data/smoke_graph.json uvicorn backend.main:app --reload --port 8000
  GRAPH_DATA_PATH=data/real_graph.json uvicorn backend.main:app --reload --port 8000
  ```

  На 5 реальных файлах в `data/raw/` секционный режим даёт **13 вызовов LLM
  вместо 322** при обработке целиком (замерено этой командой без LLM-ключа —
  подсчёт чанков не требует реального вызова API, см. `--full-document` для
  сравнения).

- **Neo4j (Cypher-хранилище графа)** — `backend/graph_store_neo4j.py` +
  `backend/neo4j_sync.py`. Единая метка `:Entity` на все узлы (тип — свойство
  `type`, не метка) и типы связей из фиксированного `RelationType` в `schema.py`.

  ```bash
  cp .env.example .env   # либо export NEO4J_PASSWORD=...
  docker compose up -d neo4j                      # bolt://localhost:7687
  python -m backend.neo4j_sync data/sample_graph.json   # или data/real_graph.json
  GRAPH_BACKEND=neo4j uvicorn backend.main:app --reload --port 8000
  ```

  `/api/health`, `/api/graph`, `/api/search`, `/api/gaps`, `/api/timeline` дают
  идентичный результат на NetworkX и на Neo4j. Neo4j Browser — http://localhost:7474.

- **FastAPI** (`backend/main.py`): `/api/graph`, `/api/graph/{id}`,
  `/api/graph/{id}/neighbors`, `/api/search`, `/api/gaps`, `/api/timeline`,
  `/api/documents/*`, `/api/rag/ask`, `/api/rag/ask/stream`,
  `/api/rag/discover-and-attach`, `/api/rag/export/pdf`.
  `GRAPH_BACKEND=networkx` (по умолчанию) или `neo4j` — см. выше.
  RAG-хранилище всегда в Neo4j — без поднятого контейнера бэкенд не стартует.
- **Frontend** (`frontend/`, React + Vite + react-force-graph-2d):
  интерактивный force-directed граф в тёмной теме — клик по узлу
  разворачивает соседей, поиск подсвечивает путь рассуждения частицами
  вдоль рёбер, тумблер «Показать пробелы в данных» рисует полупрозрачные
  пунктирные узлы для непокрытых комбинаций, связи `CONTRADICTS`
  выделяются красным пунктиром, `NEEDS_REVIEW` (авто-заподозренные конфликты
  выводов) — жёлтым пунктиром, ползунок «История во времени» анимирует
  появление экспериментов хронологически. Под строкой поиска — панель
  «База знаний для чата» (`SourcesPanel.jsx`): загрузка файла, ссылка,
  список источников. Вкладка «По документам» (`ResultsPanel.jsx`) — RAG-ответ
  с бейджем достоверности, цитатами, экспортом (PDF/Markdown/JSON) и историей
  запросов (`HistoryPanel.jsx`, `localStorage`). Лендинг: секции «Архитектура»,
  «Покрытие», «Статус требований» (`RequirementsStatus.jsx`).

- **RAG-чат по загруженным документам** (`backend/rag/`) — загрузка
  `.pdf/.docx/.txt` или ссылки через UI, чанкование (`nlp_pipeline/chunking.py`),
  эмбеддинги `paraphrase-multilingual-MiniLM-L12-v2` (локально). Вопрос из
  строки поиска параллельно уходит в граф (`/api/search`) и в RAG (`/api/rag/ask`)
  — два независимых источника на разных вкладках. Документы — узлы `:Entity
  {type: "publication"}` в Neo4j (видны на графе при `GRAPH_BACKEND=neo4j`),
  дедупликация по sha256 содержимого. Отказ вместо выдумки при низкой
  релевантности (`qa.py`). Confidence — та же логика, что `infer_confidence`
  в `graph_writer.py`. Экспорт: JSON/Markdown на клиенте (`exportAnswer.js`),
  PDF на бэкенде (`POST /api/rag/export/pdf`, `fpdf2` + DejaVu Sans для кириллицы).

## Соответствие требованиям ТЗ

| Требование | Статус |
|---|---|
| Онтология домена, граф-хранилище с обходом связей | ✅ реализовано (NetworkX; миграция на Neo4j/Gremlin — вопрос смены бэкенда графа, схема не меняется) |
| Многопараметрические запросы (материал+процесс+условие+география+период) | ✅ реализовано в `hybrid_retriever.py` |
| Числовые диапазоны и ограничения | ✅ реализовано (разбор `≤/≥/диапазон` из текста запроса) |
| Различение RU/зарубежной практики | ✅ реализовано (атрибут `country`, детектор в тексте запроса, фильтр в UI через ответ) |
| Модель верификации (источник/достоверность/дата) | ✅ атрибуты есть и отображаются в ответе и в панели деталей; workflow ручного review — не реализован |
| Визуализация графа, подсветка пробелов | ✅ реализовано |
| Подсветка противоречий (`CONTRADICTS`) | ✅ реализовано (граф + текст ответа) |
| Синтез ответов а-ля «литературный обзор» (консенсус/разногласия) | ⚠ частично: группировка по источникам и перечисление есть, авто-выделение «консенсус vs разногласие» текстом — только через противоречия, не полноценная сводка |
| NLP-пайплайн извлечения сущностей из сырых документов (RU/EN) | ✅ реализовано и прогнано вживую с YandexGPT Pro (`backend/nlp_pipeline/`, docx/pptx/pdf+OCR, chunking по языку, entity resolution, валидация, confidence-эвристика); скрипт для P/R/F1 есть (`eval.py`), но сам golden-набор для него пока не размечен |
| Экспорт PDF/Markdown/JSON-LD | ✅ реализовано |
| Дашборды для руководителей | ⚠ частично: `/api/gaps` + секция «Покрытие» на лендинге; полноценного дашборда нет |
| Сравнительные таблицы технологий | ⚠ частично: через ответ с альтернативами; отдельного UI-виджета нет |
| Мультиязычность (RU/EN) | ⚠ частично: словарь синонимов терминов; перевода запросов/документов нет |

Честная оценка: MVP с рабочей петлёй «вопрос → граф → путь рассуждения →
источники/достоверность → пробелы/противоречия» на демо-датасете
(`data/sample_graph.json`) и RAG-чатом по загруженным/проиндексированным
документам. NLP-пайплайн и Neo4j-слой реализованы и проверены на реальных
файлах; RBAC, JSON-LD и уведомления — следующий этап.

## Запуск

### Требования

- Python 3.10+
- Node.js 18+ (для frontend)
- Docker (для Neo4j — обязателен: RAG-хранилище и индексация корпуса)

```bash
cp .env.example .env          # ключи LLM, NEO4J_PASSWORD и т.д.
docker compose up -d neo4j    # bolt://localhost:7687, Browser :7474
make install                  # или: pip install -r requirements.txt && cd frontend && npm install
make sample-data              # data/sample_graph.json (один раз)
```

Опционально — serving-граф в Neo4j вместо NetworkX:

```bash
python -m backend.neo4j_sync data/sample_graph.json
GRAPH_BACKEND=neo4j make backend
```

### Backend

```bash
make backend
# или:
uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
make frontend
# или:
cd frontend && npm install && npm run dev
```

Оба сразу: `make dev`.

Откройте `http://localhost:5173`. Фронтенд обращается к бэкенду на
`http://localhost:8000` (переопределяется через `VITE_API_BASE`).

### Расширение запроса (query expand)

Перефразировки для поиска по документам: сначала облачный LLM
(Yandex Alice / GigaChat по `LLM_BACKEND`), при ошибке — fallback на локальный
Qwen через Ollama. В UI badge: «Alice · облако», «GigaChat · облако» или
«Qwen · локально». Отключить: `RAG_SKIP_QUERY_EXPAND=1`.

#### Установка Ollama

**macOS — с сайта (рекомендуется):**

1. Скачайте установщик: [https://ollama.com/download](https://ollama.com/download)
2. Установите приложение и запустите его (иконка появится в menu bar)

**macOS / Linux — через Homebrew:**

```bash
brew install ollama
ollama serve   # если сервис ещё не запущен
```

#### Модель и проверка

```bash
ollama pull qwen2.5:7b
ollama run qwen2.5:7b "Привет"          # быстрая проверка inference
curl http://localhost:11434/api/tags    # API должен вернуть JSON со списком моделей
```

Для слабого железа можно взять меньшую модель: `ollama pull qwen2.5:3b` и
указать `QUERY_EXPAND_MODEL=qwen2.5:3b` в `.env`.

#### Переменные окружения

Скопируйте из `.env.example` в `.env`:

```env
LLM_BACKEND=yandex              # или gigachat
YANDEX_API_KEY=...
YANDEX_FOLDER_ID=...
YANDEX_MODEL=aliceai-llm-flash

# fallback для query expand, если облако недоступно:
QUERY_EXPAND_BASE_URL=http://localhost:11434/v1
QUERY_EXPAND_MODEL=qwen2.5:7b
QUERY_EXPAND_TIMEOUT_SEC=15
```

После изменения `.env` перезапустите backend.

### Примеры запросов (соответствуют примерам из ТЗ)

- «Какие методы обессоливания воды подходят при сульфатах, хлоридах, Ca, Mg,
  Na по 200-300 мг/л и сухом остатке не более 1000 мг/дм3?»
- «Какие решения циркуляции католита при электроэкстракции никеля описаны
  в мировой практике, и какая скорость потока оптимальна?» (эксперименты
  на эту тему намеренно противоречат друг другу — система это подсвечивает)
- «Распределение Au, Ag и МПГ между медным/никелевым штейном и шлаком за
  последние 5 лет»
- «Какие способы закачки шахтных вод в глубокие горизонты применялись в
  России и за рубежом?»
- «Кучное выщелачивание никелевой руды в холодном климате» — намеренный
  пробел в данных (буквально пример из ТЗ), система честно сообщает об
  отсутствии данных вместо галлюцинации.

## Индексация корпуса для RAG

Корпус `data/raw/**` не входит в репозиторий (см. раздел про Яндекс.Диск
выше) — перед индексацией положите документы в `data/raw/` локально.

Двухэтапный RAG по документам из `data/raw/**`:

1. **Офлайн-индексация** — метаданные (title, authors, source, year, geography,
   language, domain, reliability_score, document_summary) + аннотация, разбитая
   на чанки с эмбеддингами в Neo4j (`index_mode=abstract`).
2. **По запросу в UI** — vector search по abstract-чанкам → top-5 документов →
   полный текст перечанкируется и прикрепляется к чату (badge «авто» в
   SourcesPanel). Auto-источники предыдущего запроса снимаются (replace);
   вручную загруженные файлы не затрагиваются.

```bash
# Neo4j должен быть запущен (docker compose up -d neo4j)
export YANDEX_API_KEY=...      # опционально — для метаданных через LLM
export YANDEX_FOLDER_ID=...

# Проиндексировать корпус (один раз или после добавления файлов)
python -m backend.scripts.index_corpus

# Переиндексация изменённых файлов — без --force; полная — с --force
python -m backend.scripts.index_corpus --force

# Смоук на N файлах
python -m backend.scripts.index_corpus --limit 5

# Только выбранные файлы (тестовый корпус из data/raw/Статьи/)
python -m backend.scripts.index_corpus \
  "data/raw/Статьи/55 Приложение. Текст статьи.docx" \
  "data/raw/Статьи/9 статья (2).docx" \
  "data/raw/Статьи/32 Статья - Салтыков П.М. (ЛГМ).docx" \
  "data/raw/Статьи/13 Приложение. Статья.pdf" \
  "data/raw/Статьи/52 Solid household and industrial waste paper 28-09-2021-rus.docx"
  
# Только выбранные файлы (тестовый корпус из data/raw/Обзоры/)
python3 -m backend.scripts.index_corpus \
  "data/raw/Обзоры/Электроэкстракция никеля. Влияние состава электролита.docx"

# Переиндексация тех же файлов принудительно — добавить --force перед путями
python3 -m backend.scripts.index_corpus --force \
  "data/raw/Статьи/55 Приложение. Текст статьи.docx" \
  "data/raw/Статьи/9 статья (2).docx" \
  "data/raw/Статьи/32 Статья - Салтыков П.М. (ЛГМ).docx" \
  "data/raw/Статьи/13 Приложение. Статья.pdf" \
  "data/raw/Статьи/52 Solid household and industrial waste paper 28-09-2021-rus.docx"

# Тестовый корпус для прогона RAG по 4 примерам из ТЗ (≤2 файла на вопрос)
python -m backend.scripts.index_corpus \
  "data/raw/Журналы/Обогащение руд/2022/ОР № 02_22.pdf" \
  "data/raw/Обзоры/Наилучшие доступные технологии последний вариант 20.08.docx" \
  "data/raw/Обзоры/Обзор технических решений в области электролитического производства никеля и меди.docx" \
  "data/raw/Обзоры/Электроэкстракция никеля. Влияние состава электролита.docx" \
  "data/raw/Обзоры/Распределение Au, Ag и МПГ между меднымникелевым штейном и шлаком.docx" \
  "data/raw/Обзоры/Переработка Cu-Ni шлаков (2024).docx" \
  "data/raw/Обзоры/Методы очистки шахтных вод.docx" \
  "data/raw/Журналы/Горный журнал/2024/№ 01_24.pdf"
```

Без аргументов скрипт сканирует весь `data/raw/**`. С явным списком путей — только указанные файлы.

**Соответствие вопросов из ТЗ и файлов корпуса** (для ручного прогона `GET /api/rag/ask` или UI):

| Вопрос из ТЗ | Файлы |
|---|---|
| Обессоливание воды ОФ (сульфаты/хлориды/Ca/Mg/Na, сухой остаток ≤1000) | `Журналы/Обогащение руд/2022/ОР № 02_22.pdf`, `Обзоры/Наилучшие доступные технологии последний вариант 20.08.docx` |
| Циркуляция католита при электроэкстракции никеля | `Обзоры/Обзор технических решений в области электролитического производства никеля и меди.docx`, `Обзоры/Электроэкстракция никеля. Влияние состава электролита.docx` |
| Распределение Au, Ag и МПГ между штейном и шлаком | `Обзоры/Распределение Au, Ag и МПГ между меднымникелевым штейном и шлаком.docx`, `Обзоры/Переработка Cu-Ni шлаков (2024).docx` |
| Закачка шахтных вод в глубокие горизонты | `Обзоры/Методы очистки шахтных вод.docx`, `Журналы/Горный журнал/2024/№ 01_24.pdf` |

### Оценка качества RAG-ответов

Набор вопросов для разметки — `data/rag_eval/questions.json` (каталог
`data/rag_eval/` в `.gitignore`, артефакты создаются локально). Пакетный прогон:

```bash
# бэкенд должен быть запущен (make backend)
python -m backend.scripts.rag_eval_batch
```

Результат для ручной разметки:

- `data/rag_eval/annotation_template.json` — ответы системы + пустые поля `gold_answer`, `rating`, `retrieval_ok`, `factual_ok`, `citation_ok`, `notes`
- `data/rag_eval/annotation_template.md` — то же в читаемом виде

**Мини-интерфейс разметки** (бэкенд + frontend dev):

```bash
make backend    # :8000
make frontend   # :5173
# открыть http://localhost:5173/eval.html
# v2 (сложные вопросы): http://localhost:5173/eval.html?v=2
# авто-оценка v2:         http://localhost:5173/eval.html?v=2&source=auto
```

Сохранение пишет `data/rag_eval/annotations.json`. Кнопка «Скачать JSON» — локальная копия.

Шкала `rating`: 1=неверно, 2=частично, 3=верно с пробелами, 4=верно, 5=эталон.

**v2 (сложнее)** — перефразированные и составные вопросы:

```bash
python -m backend.scripts.rag_eval_batch \
  --questions data/rag_eval/questions_v2.json \
  --out data/rag_eval/annotation_template_v2.json
python -m backend.scripts.rag_eval_score data/rag_eval/auto_eval_v2.json
```

Файлы: `questions_v2.json`, `annotation_template_v2.json`, `auto_eval_v2.json`.

API:

- `GET /api/rag/ask?q=...&auto_attach=true` — auto-attach + grounded ответ + граф из citation-чанков
- `GET /api/rag/ask/stream?q=...` — то же по SSE (прогресс и стриминг ответа)
- `POST /api/rag/discover-and-attach` — только подбор и прикрепление документов
- `POST /api/rag/export/pdf` — PDF-отчёт по уже полученному ответу

### Граф из citation-чанков

После RAG-ответа по **6 top citation-чанкам** вызывается `ner_extract` и строится
session-граф (префикс `rg_`, не пишется в `real_graph.json`). На главном холсте после
запроса показывается **только этот граф** (demo-граф до первого запроса сохраняется).
Узлы содержат `attrs` в JSON — карточка деталей без `/api/graph/{id}`. Если чанков
нет — холст очищается.

---

## Базовый RAG по PDF

```bash
python rag_qdrant.py --pdf path/to/file.pdf --question "..."
```

Требует `QDRANT_URL`/`QDRANT_API_KEY` и `GIGACHAT_API_KEY` в `.env`.
