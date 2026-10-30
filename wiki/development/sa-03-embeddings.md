# SA-03: Markdown и постоянные локальные эмбеддинги

← [Разработка](README.md) · [Wiki](../README.md)


Первые три шага SA-03 в `feature/sa-03-rag`, 2026-10-26. По последующему указанию пользователя поверх них реализованы retrieval, RAG и интеграция UI: актуальный сквозной сценарий описан в [поиске через приложение](sa-03-search.md). С явного разрешения загружена `qwen3-embedding:0.6b`; автоматических загрузок в приложении нет. Сравнение второй модели и расширенная приёмка остаются открытыми.

## 1. Markdown и фрагменты

`extractors.extract_document` читает `.md` в UTF-8 и передаёт в `markdown.extract_markdown`. Поддерживаются ATX (`#`) и Setext-заголовки, вложенный путь раздела (`Курс › Тема`), fenced code с backticks/tilde. Заголовки внутри fenced/indented code не становятся разделами. Исходный Markdown сохраняется в блоках; это небольшой section parser, а не полный CommonMark/GFM renderer. Front matter, HTML и вложенные списки не получают отдельной семантики.

Каждый раздел — `ExtractedBlock(source_type="markdown", heading=..., marker="line:N")`; `marker` указывает начало раздела в исходнике, а не точную строку каждого последующего фрагмента. Номера страниц для Markdown не создаются. Оригинальные файлы не изменяются.

`chunk_blocks` обрабатывает разделы отдельно. Параграфы и fenced blocks упаковываются в пределах `max_chars` (по умолчанию 1000); pipe-таблица с непрерывными строками остаётся одним параграфом. Код/таблица сохраняются целыми, если помещаются в лимит. Слишком большой структурный блок делится с обычным символьным overlap (по умолчанию 120), чтобы не нарушить жёсткий лимит. Между целыми Markdown units overlap не добавляется. Для TXT/PDF/DOCX сохраняется обычное перекрытие. `CHUNK_VERSION=2` вызывает повторную обработку ранее сохранённых документов при следующей синхронизации.

Есть необязательные `max_tokens` и `count_tokens`: вызывающий код должен передать настоящий счётчик токенов выбранной модели. Без счётчика токенный лимит не принимается. Стандартная индексация использует символьный лимит; готового tokenizer adapter нет. Токенный бюджет chunking относится к тексту фрагмента: нужно оставить место для heading и префикса. Ollama получает `truncate=false`, поэтому переполнение полного входа даёт явную ошибку, а не молчаливое усечение.

## 2. Локальный embedding runtime

`embeddings.OllamaEmbedder(model, dimensions, document_prefix="", query_prefix="")` работает только с `http://127.0.0.1:11434`. Системные HTTP-прокси и redirects отключены. Через `/api/tags` проверяются установленный tag и digest; модели с remote metadata или cloud tag отвергаются. Автоматических pull/install и облачного fallback нет. Перед и после каждого `/api/embed` digest проверяется повторно; при изменении модели batch не сохраняется.

API принимает список подготовленных входов и запрашивает размерность и `truncate=false`. Проверяются число векторов, размерность, конечность чисел и ненулевая норма. Векторы нормализуются для последующего cosine retrieval. Пустой batch не вызывает runtime. Сбой Ollama/переполнение контекста/несовместимая размерность выдаёт `EmbeddingError`; повторный запуск может продолжить с уже сохранённых batch. Отмена проверяется до и после batch, но не прерывает уже начатый HTTP-запрос (таймаут до 180 секунд).

`EmbeddingProfile` содержит имя, digest, размерность и отдельные document/query prefixes. Fingerprint включает эти параметры и `INPUT_VERSION`. Разные digest, размеры и префиксы не смешиваются. Префиксы определяются требованиями выбранной модели, не зашиты в логику. Формирование document input: `document_prefix + heading + "\n\n" + text`, либо `document_prefix + text`, если heading отсутствует. Query input: `query_prefix + question`.

## 3. SQLite и инкрементальный расчёт

Схема 2 мигрирует существующую схему 1 транзакционно, сохраняя источники, документы, chunks и FTS. Добавлены:

- `embedding_profiles`: fingerprint, model, model_digest, dimensions, document_prefix, query_prefix, input_version.
- `chunk_embeddings`: chunk_id, model_fingerprint, input_hash, dimensions, vector. Вектор — little-endian float32 BLOB; размер BLOB проверяется SQLite. Первичный ключ — `(chunk_id, model_fingerprint)`.

Новые профили хранятся рядом со старыми; автоматической очистки неиспользуемых профилей пока нет. Это не отдельная векторная БД и не индекс ближайших соседей. `load_embeddings` возвращает актуальные векторы; `retrieval_chunks` читает их вместе с текстом и метаданными для текущего retrieval.

ID фрагмента остаётся `document_id:ordinal`. `put_document` обновляет существующие ordinal вместо удаления всех фрагментов. Изменение text/heading инвалидирует векторы триггером; неизменённые ordinal сохраняют их. Удаление документа/источника каскадно удаляет векторы. Перенос текста на другой ordinal может потребовать нового расчёта: междокументного cache по одному тексту пока нет.

`EmbeddingIndexer.sync_sources(source_ids, batch_size=32, cancel_token=None)` — явно вызываемый второй этап после текстовой индексации. Он читает сохранённые chunks выбранных источников, сравнивает fingerprint и SHA-256 **полного входа**, вычисляет только отсутствующие/изменённые векторы. Инференс идёт вне транзакции SQLite. Перед записью короткая транзакция повторно проверяет текст/heading: если chunk изменился или удалён во время инференса, результат пропускается (`stale`), следующий запуск подхватит актуальный текст. Один ошибочный batch не записывается частично, ранее завершённые batch сохраняются. Обычный поиск не строит document embeddings. UI запускает второй этап при подготовке/синхронизации выбранного профиля; backend отправляет phase=embedding progress.

Пример интеграции в Python после явного выбора установленной embedding-модели:

```python
from study_agent.embeddings import EmbeddingIndexer, OllamaEmbedder
from study_agent.indexer import DocumentIndexer, source_id
from study_agent.sources import LocalFolderSource
from study_agent.storage import IndexStorage

# source_root, embedding_model и dimensions задаёт вызывающий код.
source = LocalFolderSource(source_root)
storage = IndexStorage()
DocumentIndexer(storage).sync_source(source)
embedder = OllamaEmbedder(embedding_model, dimensions)
report = EmbeddingIndexer(storage, embedder).sync_sources([source_id(source.root)])
```

Публичные DTO `Chunk` и `SearchHit` сохранены. `RetrievalResult` добавляет embedding_pending; JSONL и UI расширены согласно [контракту сквозного поиска](sa-03-search.md).

Миграция выполняется только при открытии базы новым backend; старый backend со схемой 1 отвергнет уже мигрированную базу как более новую. Пользовательские БД в ходе разработки и тестов не открываются: все проверки работают с временными синтетическими данными.

## Источники API

- [Ollama: Generate embeddings](https://docs.ollama.com/api/embed).
- [Ollama: List models](https://docs.ollama.com/api/tags).
