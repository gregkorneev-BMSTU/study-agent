# Компоненты и предварительные контракты

Это границы ответственности и возможные сигнатуры, не обязательство прямо сейчас создавать классы.

| Компонент | Ответственность | Предварительный контракт |
|---|---|---|
| `DocumentSource` | Общий протокол перечисления доступных документов и получения выбранного содержимого | `list_documents() -> Iterable[DocumentRef]`; `read(document_id) -> DocumentContent` |
| `LocalFolderSource` | Перечисление допустимых локальных путей и чтение поддерживаемых файлов | реализация `DocumentSource`; разрешённые корни задаёт пользователь |
| `IU5HubSource` | Просмотр курсов/семестров/предметов и получение выбранных материалов | реализация `DocumentSource`; сетевые ошибки и неполный каталог явны |
| `DocumentIndexer` | Извлечение текста, разбиение, метаданные и вызов эмбеддера для изменённых документов | `index(source, progress_callback) -> IndexReport` |
| `VectorStore` | Сохранение/удаление фрагментов и метаданных, запрос ближайших кандидатов | `upsert(chunks)`; `delete_source(source_id)`; `search(query_vector, filters)` |
| `MaterialRetriever` | Поиск документов и фрагментов с источниками | `retrieve(query, filters, limit) -> Sequence[RetrievedChunk]` |
| `QueryRouter` | Выбрать прямой поиск, RAG-ответ или действие | `route(query) -> SearchPlan` |
| `AnswerGenerator` | Передать локальной LLM вопрос и найденный контекст; вернуть ответ и ссылки | `generate(query, context) -> Answer` |
| `AgentExecutor` | Выполнить ограниченный план вызовов инструментов с подтверждением действий, где нужно | `execute(plan) -> ActionResult` |
| `MCPTools` | Узкий набор локальных инструментов MCP с проверкой входов и доступа | MCP-сервер/набор инструментов; контракт уточняется с первыми сценариями |

`DocumentRef`, `DocumentContent`, `Chunk`, `RetrievedChunk`, `Answer`, `IndexReport` и `SearchPlan` пока являются концептуальными DTO. Переходить к абстракциям после первого узкого end-to-end сценария.

## Внешний каталог iu5hub

Последняя проверка GitHub `gregkorneev/iu5hub` выявила TypeScript-интерфейс `MaterialsRepository`: `getSemesters()`, `getSubjects()`, `getMaterials()`, `search(query)`, `getCourses()`, `getFolder(courseId, path?)`, `getFileUrl(courseId, path)` и `searchDisk(query)`. `getFolder` возвращает элементы с именем, путём, типом и временем изменения; URL выбранного файла получает отдельный метод. Это контракт другой реализации, не Python-пакет. Условия API, загрузка файла, лимиты, доступность и правила использования должны быть перепроверены при реализации адаптера.
