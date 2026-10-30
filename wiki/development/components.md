# Компоненты и контракты

← [Разработка](README.md) · [Wiki](../README.md)


Это границы ответственности и возможные сигнатуры. Целевой продукт распространяется через GitHub и не должен зависеть от путей автора. Реальный поток SA-01 описан в [индексации документов](document-indexing.md).

| Компонент | Ответственность | Предварительный контракт |
|---|---|---|
| `DocumentSource` | Общий протокол перечисления доступных документов и получения выбранного содержимого | `list_documents() -> Iterable[DocumentRef]`; `read(document_id) -> DocumentContent` |
| `LocalFolderSource` | Перечисление допустимых локальных путей и чтение поддерживаемых файлов | Реализован в `study_agent.sources`: `.txt`/`.md`, PDF и изображения; не следует ссылкам за пределы корня |
| `IU5HubSource` | Просмотр курсов/семестров/предметов и получение выбранных материалов | реализация `DocumentSource`; сетевые ошибки и неполный каталог явны |
| `Extractor` | Извлечение текста и метаданных по формату; выбор прямого чтения либо локального OCR для сканов | Реализован в `study_agent.extractors`: PDF text-layer extraction, Chandra HF OCR для сканов и изображений, пользовательский кэш вне репозитория |
| `DocumentIndexer` | Первичная и инкрементальная индексация локального источника; отчёт, прогресс и отмена | `sync_source(source, progress_callback=None, cancel_token=None, verify_hash=False) -> IndexReport`; эмбеддер относится к SA-03 |
| `IndexStorage` | SQLite: источники, документы, фрагменты, предупреждения и лексический поиск | `IndexStorage(path=None)`; хранит пользовательскую базу вне приложения и Git |
| `chunk_blocks` | Делит `ExtractedBlock` на упорядоченные фрагменты без смешения страниц и метаданных | `chunk_blocks(blocks, max_chars=1000, overlap=120)` |
| `OllamaEmbedder` / `EmbeddingProfile` | Локальные batch-эмбеддинги и профиль модели с digest/размерностью/префиксами; без загрузки моделей | `study_agent.embeddings`; [контракт SA-03](sa-03-embeddings.md) |
| `EmbeddingIndexer` | Явный второй этап индексации сохранённых chunks; постоянные векторы в SQLite, инвалидация, batch и отмена | `sync_sources(source_ids, batch_size=32, cancel_token=None) -> EmbeddingReport` |
| `VectorStore` | Сохранение векторов реализовано в `IndexStorage` (схема 2); точный cosine retrieval реализован в `retrieval.py`, ANN пока нет | `embedding_chunks`, `put_embeddings`, `load_embeddings`; [контракт SA-03](sa-03-embeddings.md) |
| `MaterialRetriever` / `retrieve` | Lexical, exact cosine и RRF-поиск по сохранённым фрагментам выбранных источников | `retrieval.retrieve(storage, source_ids, query, mode=..., embedder=...) -> RetrievalResult` |
| `QueryRouter` | Выбрать прямой поиск, RAG-ответ или действие | `route(query) -> SearchPlan` |
| `AnswerGenerator` / `generate_answer` | Ограничить контекст, вызвать локальную модель, проверить номера ссылок и вернуть только процитированные sources либо отказ | `rag.generate_answer(model, question, hits, language=..., generator=...) -> AnswerResult` |
| `AgentExecutor` | Выполнить ограниченный план вызовов инструментов с подтверждением действий, где нужно | `execute(plan) -> ActionResult` |
| `MCPTools` | Узкий набор локальных инструментов MCP с проверкой входов и доступа | MCP-сервер/набор инструментов; контракт уточняется с первыми сценариями |
| `macOS UI` | Нативные окна поиска, библиотеки и настроек; последовательная индексация с прогрессом, статусом SQLite, повтором и отменой; проверяемые фрагменты с источниками ответа; открытие исходников | SwiftUI (`macOS/StudyAgent.xcodeproj`); модель/очередь: `StudyAgentModel`; сборка: `scripts/build_macos_native_app.sh`; детали: [нативная индексация macOS](macos-indexing-ui.md) |
| `Python Backend Bridge` | JSON Lines API между клиентом и общими Python-сервисами. В `main` команды `list_sources`, `search`, `answer`, `list_models`, `diagnose_backend`, `install_ocr_model`; формат описан в [черновике протокола](backend-protocol.md) | `study_agent.mac_bridge`; используется macOS-клиентом и подготовленной Windows-веткой |
| `PySide6 Desktop UI` | Python UI-прототип, используемый для разработки; не используется как UI нативного macOS-приложения и не является текущей Windows-оболочкой | `study_agent.ui`; запуск: `python -m study_agent` |
| `Windows UI (WinUI 3)` | Отдельный нативный Windows-клиент в незамерженной ветке; пока не является частью `main` и не прошёл платформенную приёмку | `origin/feature/sa-05-windows`; статус и расхождения протокола описаны в [черновике протокола](backend-protocol.md) |
| `AppleSwitch` | Двухпозиционный переключатель настроек с отрисовкой средствами Qt, короткой анимацией и нативной доступностью Qt checkbox | `study_agent.switch.AppleSwitch(text, compact=False, reduce_motion=False)`; использует `QCheckBox` как единственный источник состояния и сохраняет `toggled`, `stateChanged`, клавишу Space и доступное имя |
| `Ollama client` | Список установленных локальных моделей и генерация ответа по найденному материалу | `study_agent.ollama`; API только через `127.0.0.1:11434` |
| `search_sources` | Поиск и ранжирование совпадающих терминов в выбранных текстовых документах | `study_agent.search.search_sources(sources, query)`; выдаёт относительные пути и выдержки |

`DocumentRef` и `ExtractedBlock` реализованы для локального источника. Извлечение поддерживает `.txt`/`.md`, PDF, изображения и DOCX; Chandra — необязательная локальная зависимость для изображений и PDF-страниц с недостаточным текстовым слоем. SA-01 добавляет постоянный лексический индекс и инкрементальную индексацию. В локальной SA-03 реализованы точный векторный/гибридный поиск и ограниченный RAG; `QueryRouter` и агентные действия остаются будущими компонентами. См. [сквозной поиск](sa-03-search.md). Корневой путь и база хранятся только локально. Подробности OCR — в [инструкции Chandra](chandra-ocr.md).

Индекс, OCR-производные, кэш и модели не хранить в Git checkout. Тесты должны использовать синтетические fixtures; никакая карта или содержимое пользовательской папки не включается в пакет.

## Переключатель настроек

`AppleSwitch` применяется к трём бинарным параметрам внешнего вида и доступности в настройках: уменьшению прозрачности, повышенному контрасту и уменьшению движения. Обычный размер — 50×30 px, компактный — 44×26 px. Компонент рисует трек и бегунок векторно, поддерживает RTL, disabled/focus, клики по подписи и анимацию 170 мс. `set_reduce_motion(True)` останавливает анимацию и синхронно выставляет бегунок в текущее состояние.

Для совместимости с Qt и экранными дикторами компонент сохраняет роль checkbox, checked-состояние, доступное имя и клавиатурную активацию; он не меняет ключи `QSettings` и существующий обработчик настроек. Цвета передаются из текущих `ThemeTokens`; повышенный контраст усиливает неактивный трек и границу. Снимки компонента для светлой и тёмной темы находятся в [QA-папке](../../artifacts/switch-qa/README.md).

## Внешний каталог iu5hub

Последняя проверка GitHub `gregkorneev/iu5hub` выявила TypeScript-интерфейс `MaterialsRepository`: `getSemesters()`, `getSubjects()`, `getMaterials()`, `search(query)`, `getCourses()`, `getFolder(courseId, path?)`, `getFileUrl(courseId, path)` и `searchDisk(query)`. `getFolder` возвращает элементы с именем, путём, типом и временем изменения; URL выбранного файла получает отдельный метод. Это контракт другой реализации, не Python-пакет. Условия API, загрузка файла, лимиты, доступность и правила использования должны быть перепроверены при реализации адаптера.
