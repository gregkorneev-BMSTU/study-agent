# Study Agent для Windows

← [Разработка](README.md) · [Wiki](../README.md)

## Статус

Windows-клиент PR [#13](https://github.com/gregkorneev-BMSTU/study-agent/pull/13) использует WinUI 3 и общий Python backend. Обычный установщик предназначен для Windows 10/11 x64 и Windows 11 ARM64 через эмуляцию x64. Функциональное соответствие **не подтверждено**: интерактивная приёмка, OCR inference, Ollama, Narrator, high contrast и DPI на Windows не проверялись.

Тестовый установщик опубликован в отдельном prerelease [Study Agent v1 Beta 6.1 for Windows](https://github.com/gregkorneev-BMSTU/study-agent/releases/tag/v1.0.0-beta.6.1-windows). В выпуске доступны EXE и `SHA256SUMS.txt`; тег указывает на протестированный коммит `d4367675b654fe123ddddf019cfd72a085d86024`. Выпуск для macOS не менялся.

Рабочая ветка — `feature/sa-05-windows`. В неё обычным merge включён `origin/main` на `v1.0.0-beta.6.1` (`988bc365bdb7669452b20166bc3f548caa4f0996`); локальный merge-коммит: `5ac9c05`. Более нового `main` на момент проверки не было.

## Матрица соответствия Beta 6.1

| Возможность Beta 6.1 | macOS: где реализована | Windows: текущее состояние | Что требуется | Как проверяется |
|---|---|---|---|---|
| Первый запуск, приветствие, повтор мастера | `WelcomeView.swift`, `SetupWizard.swift`, `StudyAgentModel.swift` | WinUI welcome dialog на первом запуске и повтор из Settings; переход в Library | Проверить первый запуск и повтор на Windows | MSIX smoke, навигация UI |
| Диагностика backend, PDF, OCR runtime/весов и Ollama | `SetupWizard.swift`; `mac_bridge.diagnose_backend` | Команда backend и экран Library показывают состояния; OCR-веса устанавливаются только отдельной кнопкой | Проверить состав и состояния в упакованной Windows-среде | `diagnose_backend`, Windows UI |
| Ollama и локальная модель ответов | `SetupWizard.swift` | Settings открывает установку Ollama и по явному нажатию запускает `/api/pull` для `qwen3.5:4b` с прогрессом/отменой; выбранная модель сохраняется в Settings приложения | Проверить streaming-ответы и отмену на локальной Ollama | Windows с Ollama; без модели ничего не загружается автоматически |
| Язык и тема | `Localization.swift`, `StudyAgentModel.swift`, `ContentView.swift` | RU/EN сохраняются; первый язык выбирается по системной локали, неподдерживаемая локаль даёт EN; system/light/dark | Проверить смену языка и темы после перезапуска | Установленный MSIX |
| Доступность | `ContentView.swift`, `WelcomeView.swift` | WinUI элементы доступны клавиатуре; Settings открывает системные страницы Windows для Contrast themes и Reduce motion; интерфейс использует системные theme resources | Проверить Narrator, клавиатуру, high contrast и анимации | Windows с Narrator и настройками доступности |
| Папки библиотеки | `StudyAgentModel.addFolders`, `refreshSources` | FolderPicker добавляет несколько корней повторными выборами, список сохраняется в пользовательских данных, добавление запускает начальную индексацию | Проверить восстановление и длинные/кириллические пути | Windows UI + синтетическая папка |
| Индексация, прогресс, отмена, ошибки, повтор | `StudyAgentModel.indexFolders`, `ContentView` | Используются `sync_source`, события JSONL `progress`, реальные счётчики, отмена дочернего дерева; `Check for Changes` повторяет изменённые/ошибочные документы; `index_status.issues` показывается по документам | Проверить очередность, состояние после перезапуска и сбои отдельных файлов | Windows UI; backend synthetic smoke |
| Отключение папки | `removeIndexedSource` | Сначала вызывается `remove_index_source`; сохранённый путь убирается только после успешного удаления. Исходники не удаляются | Проверить ошибку удаления и повтор | Windows + временная SQLite |
| Недоступный источник | `StudyAgentModel.search`, `mac_bridge` | Поиск использует сохранённый индекс, не пытается синхронизировать офлайн-папку; список показывает недоступность и сохранённый индекс | Проверить совместное использование доступного и офлайн-источника | Упакованный backend smoke и Windows UI |
| Лексический, семантический и гибридный поиск | `StudyAgentModel.search`, `retrieval.py` | WinUI передаёт режим, установленный embedding-профиль и roots; есть явная команда подготовки векторного индекса; при недоступном embedding runtime остаётся lexical | Проверить embeddings на Windows/Ollama; сейчас только общий Python backend покрыт тестами | `tests/test_retrieval.py`, Windows с локальным Ollama |
| RAG и проверенные ссылки | `mac_bridge.answer`, `rag.py`, `StudyAgentModel` | Передаются roots/query/language/режим; backend повторно выбирает источники из SQLite и валидирует citations; UI показывает только `result.sources`, результаты поиска остаются при ошибке генерации | Проверить локальную модель и citations в WinUI | Backend tests и ручной Windows smoke |
| Открытие источника и метаданные | `ContentView.swift` | Карточка показывает PDF page/DOCX heading и раскрываемый исходный фрагмент; открытие файла ограничено выбранным корнем | Проверить Windows default app и путь с кириллицей | Windows UI |
| TXT/Markdown/PDF/DOCX/изображения/OCR Beta 6.1 | `extractors.py`, `ocr_model.py`, release notes Beta 6.1 | Клиент использует общий backend: текстовый PDF плюс OCR каждой страницы, встроенные DOCX изображения, вложенные Markdown изображения внутри корня. Runtime/веса включаются/загружаются отдельно скриптом и действием UI | Не подтверждена работа Chandra inference на Windows x64; см. раздел OCR | Synthetic Python tests и обязательный Windows OCR smoke |
| Markdown и LaTeX | `MathContentView.swift`, локальный KaTeX в `assets/math` | Локальный WebView2 renderer использует тот же безопасный Markdown subset и KaTeX, без HTML из источника, ссылок, CDN или сетевых ресурсов; при ошибке остаётся обычный текст | Проверить CSP, вертикальную прокрутку WebView2 и длинные формулы | JS/Python renderer tests, Windows WebView2 |
| Release пакет и установка | `scripts/build_macos_dmg.sh` (macOS) | WinUI Release включает backend, локальные ресурсы и notices; автономный EXE-установщик ставит приложение в профиль пользователя; отдельный unsigned MSIX остаётся доступен для сборки | Проверить установку и работу на Windows 10/11 x64 и Windows 11 ARM64 | GitHub Actions и ручная приёмка |

Порог сходства (по умолчанию 0.65) и префиксы embedding-модели настраиваются в Settings (`SearchPreferences.cs`) и передаются в `search`/`answer` как `min_similarity` и `embedding.document_prefix`/`query_prefix`. Сборка WinUI с этими правками не запускалась (нет Windows/.NET).

### Доработки паритета с macOS (не собирались на Windows)

- **Карточки результатов.** Backend уже возвращает одну запись на файл с `matched_excerpts`; карточка показывает имя файла, `корень/путь`, страницу/раздел и раскрываемый `Original Text`. Фрагменты рендерит `Controls/RenderedMarkdownView.cs` (локальный WebView2 + KaTeX, создаётся лениво при раскрытии, при сбое остаётся простой текст). После ответа на карточках использованных файлов появляется номер цитаты `[n]` из `result.sources`, а блок источников в тексте ответа больше не дублируется.
- **Горячие клавиши.** Ctrl+F — раздел поиска и фокус на запросе, Ctrl+O — раздел библиотеки и выбор папки.
- **Диагностика.** Кнопка проверки backend добавляет версию Windows, архитектуру, память и свободное место (`Services/SystemInfoService.cs`); перед загрузкой модели показывается предупреждение, если свободно меньше 5 ГБ.
- **Осознанное отличие от macOS.** Очередь отложенных удалений не добавлялась: при ошибке `remove_index_source` источник остаётся в списке и индекс не скрывается, пользователь повторяет удаление вручную. Значок в трее и Ctrl+, не реализованы.

### OCR и ограничения Chandra

В `pyproject.toml` Chandra — optional extra. `scripts/build_windows_backend.ps1` теперь требует `.[ocr,packaging]` и включает Chandra/Hugging Face/Torch/PDF/OCR runtime в PyInstaller archive; веса остаются отдельными и загружаются только по нажатию **Install OCR weights**. Действие недоступно, пока диагностика не увидела runtime или если веса уже установлены.

Официальный upstream Chandra описывает локальный Hugging Face запуск и `chandra-ocr[hf]`, но в upstream issues есть открытое сообщение о `NotImplementedError` при CPU inference на Windows 10. Это свидетельство известного сценария, не доказательство, что все Windows-конфигурации не работают. В этой задаче нет Windows-машины, поэтому совместимость пакета, CUDA/CPU-путь, PyInstaller импортов и inference не проверены. Не считать OCR на Windows доступным для выпуска до прохождения Windows CI сборки и локального сканированного PDF/DOCX smoke. Модели и веса не включаются в Git или пакет и не скачиваются автоматически.

Chandra weights имеют ограничения Modified OpenRAIL-M, указанные в `THIRD_PARTY_NOTICES.md`; перед распространением весов или производных результатов следует проверить актуальные условия. Веса не распространяются вместе с приложением.

## Исправления замечаний ревью PR #13

1. **Backend ZIP:** исправлено — `package_windows_backend.py` создаёт `build/windows-backend/StudyAgentBackend.zip`; Release build останавливается с ошибкой, если его нет.
2. **Удаление индекса:** исправлено — WinUI выполняет `remove_index_source` до удаления источника из списка; ошибка оставляет источник подключённым.
3. **Офлайн-папка:** исправлено — перед поиском больше нет обязательного sync каждого пути; CI synthetic smoke подтвердил retrieval по сохранённому SQLite индексу после перемещения папки.
4. **Предупреждения:** исправлено на уровне UI-кода — библиотека читает восстановленные `index_status.issues`, поиск показывает `warnings`, индексация показывает ошибки файлов и счётчики.
5. **Источники:** исправлено на уровне UI-кода — результат открывает файл в системном приложении, показывает page/heading, полный исходный фрагмент и только проверенные RAG sources.
6. **Язык ответа:** исправлено — передаётся выбранный `ru`/`en`; контекст ответа извлекает backend из индекса, клиентские `hits` больше не используются.
7. **Первичная индексация:** исправлено — добавление папки вызывает `sync_source` с прогрессом; действие отмены оставляет доступные записи и допускает повтор.
8. **Русский текст и таймаут:** испорченные строки заменены; ошибка таймаута использует фактический лимит конкретной операции. CI smoke также обнаружил, что упакованный backend читал JSONL stdin не как UTF-8; runtime hook теперь явно перенастраивает stdin, после чего Cyrillic-path smoke прошёл.

Это статус реализации по коду с учётом успешного Windows CI smoke/build. Полное подтверждение пользовательских сценариев зависит от установки и проверки Release MSIX в интерактивной Windows-среде.

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
dotnet publish .\windows\StudyAgent.Windows\StudyAgent.Windows.csproj -c Release -r win-x64 -p:Platform=x64 -p:WindowsPackageType=None --self-contained true -o .\build\windows-publish
choco install innosetup --no-progress -y
.\scripts\build_windows_installer.ps1
```

Скрипт останавливается, если нет backend executable, runtime или архива. Release MSIX unsigned; тестовый сертификат не является публично доверенной подписью. SmartScreen и установка на чистой Windows не подтверждены. Для пользовательского запуска Python и зависимости проекта не нужны. Обычная установка сохраняет настройки, список папок, индекс и установленные пользователем Chandra weights в `%LOCALAPPDATA%\StudyAgent`; MSIX продолжает использовать свой `LocalState\StudyAgent`. Данные двух вариантов не переносятся автоматически. Деинсталлятор не удаляет пользовательские данные.

Новый `StudyAgentSetup.exe` устанавливает автономное приложение в `%LOCALAPPDATA%\Programs\Study Agent`, создаёт ярлык и деинсталлятор; Python вручную устанавливать не требуется. Установщик и приложение не подписаны публично доверенным сертификатом, поэтому Windows может показать предупреждение. Сборка предназначена для теста. Старый установщик из run 40771990479 отклонял ARM64 и использовал неподписанный MSIX; не используйте его для новой проверки. Сам `.exe` не хранится в Git из-за размера и публикуется как Actions artifact.

Для Markdown и формул используется системный WebView2 Runtime. Если он отсутствует, установщик запускает вложенный подписанный Microsoft bootstrapper, которому нужен интернет для загрузки компонента; документы и модели при этом не отправляются. Само отображение работает локально. Проверка Windows 10 на чистой системе и без WebView2 остаётся открытой. Минимальная версия по настройкам приложения и установщика — Windows 10 build 17763. Поддержка .NET 10 для Windows 10 ограничена актуальными редакциями LTSC/Enterprise согласно [документации Microsoft](https://learn.microsoft.com/en-us/dotnet/core/install/windows).

Backend smoke создаёт временные кириллические TXT/Markdown материалы и проверяет diagnostics, JSONL progress, индексацию, поиск при выключенном источнике, статус и физическое удаление производных записей. Тест использует временную базу и удаляет каталог после завершения.

## Фактические проверки в текущей среде

- Для пробы скачайте artifact `study-agent-windows-setup` из [Actions run 40780072886](https://github.com/gregkorneev-BMSTU/study-agent/actions/runs/40780072886) и извлеките `StudyAgentSetup.exe` из ZIP. Размер ZIP — 395,680,424 байта, SHA-256 `a413c2f5816969ee34d5c1667d5c748e77ded704a83594fae859f70fe6d87ad4`. Вход в GitHub может потребоваться. Срок хранения артефакта истекает 27 января 2027 года в 01:27 по Москве.
- В этом run на Windows Server 2022 x64 (build 20348) и Windows 11 ARM64 (build 26200, x64 emulation) успешно проверены установка, распаковка backend архивом .NET, synthetic backend smoke, запуск процесса приложения на 15 секунд, деинсталляция и сохранение файла пользовательских данных. Интерактивная работа UI и Windows 10 не проверены.
- Общий статус этого run — failure: Linux pytest не смог импортировать тестовый скрипт из `scripts`. Импорт исправлен следующим коммитом `3cda0ad`; он изменяет только тест, а не файлы приложения, использованные в этом установщике. Повторный [run 40781291563](https://github.com/gregkorneev-BMSTU/study-agent/actions/runs/40781291563) полностью прошёл, включая Linux и оба Windows installer smoke.
- Старые artifact из run 40771990479 и 40777451857 не следует использовать: первый отклоняет ARM64, а оба содержат архив backend с повторяющимися путями лицензий.

- Host: macOS 27 arm64, Python 3.12.15. Windows/.NET/PowerShell отсутствуют.
- `.venv/bin/python -m ruff check .` — успешно.
- `.venv/bin/python -m pytest -q tests/test_windows_packaging.py` — 1 passed.
- `.venv/bin/pytest -q tests/test_mac_bridge.py tests/test_ocr_model.py tests/test_windows_packaging.py` — 24 passed; проверено локально после финального исправления UTF-8 stdin.
- Обычный полный `pytest` аварийно завершился при инициализации Qt Cocoa в `tests/test_switch.py`; повтор с offscreen завершился так же. Прогон с игнорированием этой fixture и неотслеживаемых копий `* [0-9].py` дошёл до `tests/test_ui_retrieval.py::test_material_text_uses_plain_text_and_offers_original` и аварийно завершил Qt. Полного успешного результата pytest нет.
- [GitHub Actions run 40771990479](https://github.com/gregkorneev-BMSTU/study-agent/actions/runs/40771990479) — предыдущая сборка: Linux/Windows pytest и Ruff, WinUI Debug, backend smoke, unsigned MSIX, Inno Setup и macOS client checks/build; его EXE устарел.
- CI artifact `study-agent-windows-release-unsigned` создан (743,843,681 bytes; SHA-256 `d52af6c2bc8390f4dc8ede0dbb12ec400440ed21ecf66ee8d135ef2c711315c0`). Это unsigned build artifact, не подписанный публично доверенным сертификатом и не проверенный установкой.
- Интерактивные установка и работа приложения на Windows 10/11, SmartScreen, Chandra inference, Ollama generation/streaming, Narrator/high contrast и масштабирование 150–200% на Windows не проверены.

Приёмка на Windows остаётся обязательной. Нельзя считать функциональное соответствие подтверждённым до проверки установленного Release MSIX на Windows с TXT, Markdown, цифровым/сканированным PDF, DOCX со встроенным изображением, локальными изображениями Markdown, отменой, ошибками/повторами, lexical/semantic/hybrid, RAG citations, OCR после явной установки весов, открытием исходника и доступностью.
