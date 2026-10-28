# Study Agent для Windows

## Статус

Windows-клиент PR [#13](https://github.com/gregkorneev-BMSTU/study-agent/pull/13) использует WinUI 3 и общий Python backend. Локально подтверждены кодовые изменения для Beta 6.1, но функциональное соответствие **не подтверждено**: в текущей среде нет Windows, .NET SDK или PowerShell, Release MSIX и UI не запускались.

Рабочая ветка — `feature/sa-05-windows`. В неё обычным merge включён `origin/main` на `v1.0.0-beta.6.1` (`988bc365bdb7669452b20166bc3f548caa4f0996`); локальный merge-коммит: `5ac9c05`. Более нового `main` на момент проверки не было.

## Матрица соответствия Beta 6.1

| Возможность Beta 6.1 | macOS: где реализована | Windows: текущее состояние | Что требуется | Как проверяется |
|---|---|---|---|---|
| Первый запуск, приветствие, повтор мастера | `WelcomeView.swift`, `SetupWizard.swift`, `StudyAgentModel.swift` | WinUI welcome dialog на первом запуске и повтор из Settings; переход в Library | Проверить первый запуск и повтор на Windows | MSIX smoke, навигация UI |
| Диагностика backend, PDF, OCR runtime/весов и Ollama | `SetupWizard.swift`; `mac_bridge.diagnose_backend` | Команда backend и экран Library показывают состояния; OCR-веса устанавливаются только отдельной кнопкой | Проверить состав и состояния в упакованной Windows-среде | `diagnose_backend`, Windows UI |
| Ollama и локальная модель ответов | `SetupWizard.swift` | Settings открывает установку Ollama и по явному нажатию запускает `/api/pull` для `qwen3.5:4b` с прогрессом/отменой; выбранная модель сохраняется в Settings приложения | Проверить streaming-ответы и отмену на локальной Ollama | Windows с Ollama; без модели ничего не загружается автоматически |
| Язык и тема | `Localization.swift`, `StudyAgentModel.swift`, `ContentView.swift` | RU/EN сохраняются; первый язык выбирается по системной локали, неподдерживаемая локаль даёт EN; system/light/dark | Проверить смену языка и темы после перезапуска | Установленный MSIX |
| Доступность | `ContentView.swift`, `WelcomeView.swift` | WinUI элементы доступны клавиатуре; Settings открывает системные страницы Windows для Contrast themes и Reduce motion; интерфейс использует системные theme resources | Проверить Narrator, клавиатуру, high contrast и анимации | Windows с Narrator и настройками доступности |
| Папки библиотеки | `StudyAgentModel.addFolders`, `refreshSources` | FolderPicker добавляет несколько корней повторными выборами, список сохраняется в MSIX LocalState, добавление запускает начальную индексацию | Проверить восстановление и длинные/кириллические пути | Windows UI + синтетическая папка |
| Индексация, прогресс, отмена, ошибки, повтор | `StudyAgentModel.indexFolders`, `ContentView` | Используются `sync_source`, события JSONL `progress`, реальные счётчики, отмена дочернего дерева; `Check for Changes` повторяет изменённые/ошибочные документы; `index_status.issues` показывается по документам | Проверить очередность, состояние после перезапуска и сбои отдельных файлов | Windows UI; backend synthetic smoke |
| Отключение папки | `removeIndexedSource` | Сначала вызывается `remove_index_source`; сохранённый путь убирается только после успешного удаления. Исходники не удаляются | Проверить ошибку удаления и повтор | Windows + временная SQLite |
| Недоступный источник | `StudyAgentModel.search`, `mac_bridge` | Поиск использует сохранённый индекс, не пытается синхронизировать офлайн-папку; список показывает недоступность и сохранённый индекс | Проверить совместное использование доступного и офлайн-источника | Упакованный backend smoke и Windows UI |
| Лексический, семантический и гибридный поиск | `StudyAgentModel.search`, `retrieval.py` | WinUI передаёт режим, установленный embedding-профиль и roots; есть явная команда подготовки векторного индекса; при недоступном embedding runtime остаётся lexical | Проверить embeddings на Windows/Ollama; сейчас только общий Python backend покрыт тестами | `tests/test_retrieval.py`, Windows с локальным Ollama |
| RAG и проверенные ссылки | `mac_bridge.answer`, `rag.py`, `StudyAgentModel` | Передаются roots/query/language/режим; backend повторно выбирает источники из SQLite и валидирует citations; UI показывает только `result.sources`, результаты поиска остаются при ошибке генерации | Проверить локальную модель и citations в WinUI | Backend tests и ручной Windows smoke |
| Открытие источника и метаданные | `ContentView.swift` | Карточка показывает PDF page/DOCX heading и раскрываемый исходный фрагмент; открытие файла ограничено выбранным корнем | Проверить Windows default app и путь с кириллицей | Windows UI |
| TXT/Markdown/PDF/DOCX/изображения/OCR Beta 6.1 | `extractors.py`, `ocr_model.py`, release notes Beta 6.1 | Клиент использует общий backend: текстовый PDF плюс OCR каждой страницы, встроенные DOCX изображения, вложенные Markdown изображения внутри корня. Runtime/веса включаются/загружаются отдельно скриптом и действием UI | Не подтверждена работа Chandra inference на Windows x64; см. раздел OCR | Synthetic Python tests и обязательный Windows OCR smoke |
| Markdown и LaTeX | `MathContentView.swift`, локальный KaTeX в `assets/math` | Локальный WebView2 renderer использует тот же безопасный Markdown subset и KaTeX, без HTML из источника, ссылок, CDN или сетевых ресурсов; при ошибке остаётся обычный текст | Проверить CSP, вертикальную прокрутку WebView2 и длинные формулы | JS/Python renderer tests, Windows WebView2 |
| Release пакет и установка | `scripts/build_macos_dmg.sh` (macOS) | WinUI Release включает `StudyAgentBackend.zip`, локальные ресурсы математики и notices; ZIP содержит PyInstaller runtime и доступные лицензии; CI запускает synthetic backend smoke и строит unsigned MSIX | Успешная CI и чистая установка Windows ещё не получены | GitHub Actions, затем установленный MSIX |

### OCR и ограничения Chandra

В `pyproject.toml` Chandra — optional extra. `scripts/build_windows_backend.ps1` теперь требует `.[ocr,packaging]` и включает Chandra/Hugging Face/Torch/PDF/OCR runtime в PyInstaller archive; веса остаются отдельными и загружаются только по нажатию **Install OCR weights**. Действие недоступно, пока диагностика не увидела runtime или если веса уже установлены.

Официальный upstream Chandra описывает локальный Hugging Face запуск и `chandra-ocr[hf]`, но в upstream issues есть открытое сообщение о `NotImplementedError` при CPU inference на Windows 10. Это свидетельство известного сценария, не доказательство, что все Windows-конфигурации не работают. В этой задаче нет Windows-машины, поэтому совместимость пакета, CUDA/CPU-путь, PyInstaller импортов и inference не проверены. Не считать OCR на Windows доступным для выпуска до прохождения Windows CI сборки и локального сканированного PDF/DOCX smoke. Модели и веса не включаются в Git или пакет и не скачиваются автоматически.

Chandra weights имеют ограничения Modified OpenRAIL-M, указанные в `THIRD_PARTY_NOTICES.md`; перед распространением весов или производных результатов следует проверить актуальные условия. Веса не распространяются вместе с приложением.

## Исправления замечаний ревью PR #13

1. **Backend ZIP:** исправлено — `package_windows_backend.py` создаёт `build/windows-backend/StudyAgentBackend.zip`; Release build останавливается с ошибкой, если его нет.
2. **Удаление индекса:** исправлено — WinUI выполняет `remove_index_source` до удаления источника из списка; ошибка оставляет источник подключённым.
3. **Офлайн-папка:** исправлено — перед поиском больше нет обязательного sync каждого пути; backend выполняет retrieval по сохранённому SQLite индексу.
4. **Предупреждения:** исправлено на уровне UI-кода — библиотека читает восстановленные `index_status.issues`, поиск показывает `warnings`, индексация показывает ошибки файлов и счётчики.
5. **Источники:** исправлено на уровне UI-кода — результат открывает файл в системном приложении, показывает page/heading, полный исходный фрагмент и только проверенные RAG sources.
6. **Язык ответа:** исправлено — передаётся выбранный `ru`/`en`; контекст ответа извлекает backend из индекса, клиентские `hits` больше не используются.
7. **Первичная индексация:** исправлено — добавление папки вызывает `sync_source` с прогрессом; действие отмены оставляет доступные записи и допускает повтор.
8. **Русский текст и таймаут:** испорченные строки заменены; ошибка таймаута использует фактический лимит конкретной операции.

Это статус реализации по коду. Полное подтверждение каждого пункта зависит от Windows CI и ручного MSIX теста.

## Сборка

Требования: Windows x64, Python 3.12, .NET 10 SDK, Windows App SDK из NuGet. Python нужен только для сборки; приложение упаковывает backend.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install ".[dev,ocr,packaging]"
.\scripts\build_windows_backend.ps1
.\scripts\smoke_windows_backend.ps1
dotnet build .\windows\StudyAgent.Windows\StudyAgent.Windows.csproj -c Debug -r win-x64 -p:Platform=x64
dotnet build .\windows\StudyAgent.Windows\StudyAgent.Windows.csproj -c Release -r win-x64 -p:Platform=x64 -p:GenerateAppxPackageOnBuild=true -p:AppxPackageSigningEnabled=false
```

Скрипт останавливается, если нет backend executable, runtime или архива. Release MSIX unsigned; `CN=AppPublisher` test certificate не является публично доверенной подписью. SmartScreen и установка на чистой Windows не подтверждены. Для пользовательского запуска Python и зависимости проекта не нужны. Пользовательские настройки/список папок/индекс и загруженные по явному действию Chandra weights располагаются в MSIX `LocalState\StudyAgent`; исходные материалы остаются в подключённых папках.

Backend smoke создаёт временные кириллические TXT/Markdown материалы и проверяет diagnostics, JSONL progress, индексацию, поиск при выключенном источнике, статус и физическое удаление производных записей. Тест использует временную базу и удаляет каталог после завершения.

## Фактические проверки в текущей среде

- Host: macOS 27 arm64, Python 3.12.15. Windows/.NET/PowerShell отсутствуют.
- `.venv/bin/python -m ruff check .` — успешно.
- `.venv/bin/python -m pytest -q tests/test_windows_packaging.py` — 1 passed.
- Обычный полный `pytest` аварийно завершился при инициализации Qt Cocoa в `tests/test_switch.py`; повтор с offscreen завершился так же. Прогон с игнорированием этой fixture и неотслеживаемых копий `* [0-9].py` дошёл до `tests/test_ui_retrieval.py::test_material_text_uses_plain_text_and_offers_original` и аварийно завершил Qt. Полного успешного результата pytest нет.
- WinUI Debug/Release, PowerShell packaging script, bundled backend smoke, MSIX install, Chandra inference, Ollama streaming и accessibility на Windows не запускались.
- GitHub Actions для новых коммитов этой задачи пока не выполнен; синтетический скрипт настроен в Windows CI PR #13.

Приёмка на Windows остаётся обязательной. Нельзя считать функциональное соответствие подтверждённым до проверки установленного Release MSIX на Windows с TXT, Markdown, цифровым/сканированным PDF, DOCX со встроенным изображением, локальными изображениями Markdown, отменой, ошибками/повторами, lexical/semantic/hybrid, RAG citations, OCR после явной установки весов, открытием исходника и доступностью.
