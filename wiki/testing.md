# Тестирование

## SA-03: математическая выдача и диагностика (2026-10-26)

Полный pytest: **203 passed**; `ruff check .` прошёл. Регрессии покрывают группировку, корень/обратный корень/степени и sin/cos, сохранение условий и отрицаний, код и числа внутри формул, подозрительные формулы, подробные ошибки и совместимость клиентов. Swift model_queue и реальный WKWebView math_render harness прошли; последний проверяет MathML, исходный код, HTML injection, ограничения макросов, запрет сетевых ресурсов и тёмную схему. Штатная Xcode/PyInstaller сборка и строгая подпись прошли. Реальная локальная Ollama на синтетических данных вернула одну подходящую формулу и ответ с одним источником: [QA](../artifacts/sa-03-search-qa/README.md). Полная визуальная проверка приложения через CUA остаётся ограничена сбоем native pipe; математическая корректность произвольных материалов не доказана.

## Исправления после ревью PR #11 (2026-10-25)

PySide6 начинает инкрементальную индексацию в рабочем потоке сразу после добавления папки и повторяет её для сохранённых источников при запуске. Поиск, индексация и удаление источника проходят через одну очередь. Папка исчезает из сохранённой библиотеки только после успешного удаления текста из SQLite; при ошибке она остаётся доступной для повтора. Тест `test_ui_index.py` проверяет добавление, появление и удаление текста, ошибку удаления и порядок запуска задач. При большом корпусе поиск ждёт завершения текущей индексации; длительность OCR отдельно не измерялась.

Пути macOS-источников приводятся к каноническому виду при сохранении и при чтении доступной папки. Swift-тест создаёт символическую ссылку и проверяет, что путь для поиска совпадает с путём целевой папки. Отдельный Swift-тест компилирует `StudyAgentModel` и через подменный backend проверяет повтор индексации и удаления после временного сбоя. CI дополнительно собирает всё macOS-приложение. Путь ранее сохранённой ссылки, цель которой уже недоступна, нельзя канонизировать до восстановления доступа.

Локально полный `pytest -q` с временной копией Qt platform plugins без флага `hidden` — **72 passed**; `ruff check .`, обе Swift-проверки и Debug `xcodebuild` прошли. [CI для последнего коммита PR #11](https://github.com/gregkorneev-BMSTU/study-agent/actions/runs/40207795289) прошёл на Python 3.12, 3.13 и macOS. Физическое отключение диска во время индексации остаётся ручным сценарием.

## SA-01: постоянный индекс

Новые синтетические тесты используют временную SQLite-базу и TXT/MD-файлы. Они проверяют первичную и повторную индексацию, замену изменённого текста без старых поисковых записей, добавление и удаление файлов, повторное открытие базы, Unicode и одинаковые имена в разных источниках, ошибку отдельного документа, отмену и продолжение, недоступный корень и поиск без вызова `source.read()`. Отдельно проверяются границы фрагментов и сохранение страницы/маркера. Обычный CI не загружает OCR-веса или Qwen. Точные результаты последнего запуска приводятся только после выполнения проверок в этой ветке.

Регрессия поиска с отключённым источником проверяется через JSON bridge: после создания индекса папка исчезает, а запрос по сохранённому пути всё равно возвращает фрагмент. macOS-клиент передаёт сохранённые пути без открытия bookmark; SwiftUI-сценарий с реально отозванной закладкой требует ручной проверки в приложении.

Для macOS-клиента добавлена отдельная Swift-проверка: сохранённый путь работает при повреждённой bookmark, ошибка одной старой bookmark не прерывает выбор других путей, а старый формат настроек читается. GitHub CI запускает её на macOS. Повтор после ошибок backend проверяется подменным backend; реальное отключение источника требует ручной проверки.

Локальная проверка последнего исправления PR #11: Swift-проверка прошла, Release `xcodebuild` прошёл, `pytest -q --ignore=tests/test_switch.py` — 65 passed, `ruff check .` — успешно. Последующее расследование Qt-сбоя позволило запустить весь набор: **68 passed** с отдельным каталогом платформенных плагинов.

Причина прежнего `Fatal Python error: Aborted` в `tests/test_switch.py` установлена: у `libqminimal.dylib`, `libqoffscreen.dylib` и `libqcocoa.dylib` внутри локальной `.venv` выставлен macOS-флаг `hidden`. Qt перечисляет каталог `PySide6/Qt/plugins/platforms` без скрытых файлов и сообщает, что не нашёл плагин `minimal`; аварийное завершение происходит до выполнения кода теста. Копии `libqminimal.dylib` и `libqoffscreen.dylib` во временном каталоге без флага `hidden` и переменная `QT_QPA_PLATFORM_PLUGIN_PATH`, указывающая на него, дали полный результат `pytest -q`: **68 passed**. Эта особенность локальной установки PySide6 не воспроизводилась в GitHub CI. Физическое отключение диска в нативном приложении отдельно не проверялось; для него нужен установленный backend и выбранный съёмный источник.

## Автоматические проверки

Минимальная CI матрица запускает Python 3.12 и 3.13, `pytest` и `ruff check .`; целевая матрица должна покрывать Windows и macOS, как только зависимости позволяют это надёжно сделать. CI не скачивает модели и не требует Ollama/Chandra weights. Локально запускаются те же команды из README после установки `.[dev]`.

Текущие тесты покрывают `LocalFolderSource`, OCR-маршрутизацию страниц PDF и локальный кэш. Проверки используют подменённый PDF renderer и OCR, не загружают Chandra weights и не проверяют точность модели.

Проверка упаковки 2026-10-25: установленная Beta 3 аварийно завершала backend на реальной папке со сканированными PDF. Причина — отсутствие нативного расширения `torchvision` и соседних `.dylibs` в PyInstaller bundle. После исправления скрипта сборки новый `.app` прошёл `codesign --verify --deep --strict`, а упакованный backend вернул корректный JSON для текстового поиска. На сканированном PDF процесс перешёл к загрузке весов OCR и не завершился прежней ошибкой импорта в течение 15 секунд. Полный OCR и качество распознавания в этой проверке не подтверждены.

Для v1 Beta 1 добавлены unit-тесты команды `diagnose_backend` в JSON Lines bridge: проверяется формат ответа и определение доступности библиотек без запуска или загрузки весов Chandra. Мастер SwiftUI, системные действия Ollama, загрузка модели и оформление Finder требуют отдельной проверки на реальном Mac. Стандартные Python-тесты не скачивают модели.

## PR #7 — macOS навигация, onboarding и CI (включён в Beta 3)

- В отдельной Xcode сборке проверены `NavigationSplitView`, переключение Search/Library и отсутствие пустой области. Debug/Release собраны на macOS 27 с deployment target macOS 14; проверка macOS 14/15 не проводилась.
- В QA Release UI пройдены три welcome-страницы, английский/русский текст и переход в технический SetupWizard в том же sheet. Реальные скриншоты не сохранены, потому что системный захват экрана возвращал lock screen. VoiceOver, полный keyboard-only сценарий и Reduce Motion не прошли отдельный аудит.
- AppKit `NSMenuItem.title` менялся согласно выбранному языку, но accessibility snapshot продолжал отдавать английские названия верхнего меню. Нужна визуальная и доступностная перепроверка.
- CI run [40129362779](https://github.com/gregkorneev-BMSTU/study-agent/actions/runs/40129362779) подтвердил `ModuleNotFoundError: tqdm` в `tests/test_ocr_model.py`: workflow устанавливал `.[dev]`, где пакета не было. `tqdm>=4.66,<5` добавлен в dev extra коммитом `eee1b3e` в `main`; последующий run [40129447523](https://github.com/gregkorneev-BMSTU/study-agent/actions/runs/40129447523) прошёл pytest и Ruff на Python 3.12/3.13.
- На Mac с Python 3.12.15 `pytest --ignore=tests/test_switch.py` — 31 passed; Ruff прошёл. Полный локальный pytest не удалось проверить из-за аварии Qt Cocoa plugin в тесте `tests/test_switch.py`.

Проверка 2026-10-24 перед выпуском: Release arm64 `xcodebuild` прошёл; `ruff check .` прошёл; `pytest --ignore=tests/test_switch.py` — 27 passed. Полный локальный `pytest -q` остановился с `Fatal Python error: Aborted` в `tests/test_switch.py` при создании `QApplication` на текущей macOS/PySide6; это ограничение локальной Qt-проверки, а не результат тестов SwiftUI. GitHub CI ранее падал на Ubuntu при импорте PySide6 из-за отсутствия `libEGL.so.1`; после добавления Qt runtime библиотек [CI для коммита `ce7d36c`](https://github.com/gregkorneev-BMSTU/study-agent/actions/runs/40080888078) успешно выполнил полный `pytest` и Ruff на Python 3.12 и 3.13.

Финальный тестовый DMG `StudyAgent-v1.0.0-beta.1-macos-arm64.dmg`: `hdiutil verify` подтвердил checksum образа; при монтировании в корне только `Study Agent.app`, `Applications → /Applications` и скрытая `.DS_Store`; `Info.plist` показывает 1.0.0 (build 1); `codesign --verify --deep --strict` прошёл для ad-hoc подписи; упакованный helper ответил на `diagnose_backend` с доступными PDF/OCR runtime и `ocr_weights_state=unknown`. Приложение скопировано из DMG во временную папку с пробелом в пути и запущено отдельным процессом. Пробный образ в Finder сохранял окно 660 × 380 pt, позиции значков и размер 128 pt. Светлая тема, запуск на чистом Mac, Gatekeeper, нотариализация и фактическая загрузка больших моделей этим прогоном не подтверждены.

## Проверка SwiftUI Liquid Glass refresh

24.10.2026, Xcode 27.1 / macOS SDK 27.0 на macOS 27.0.1 (arm64):

- Отдельная Debug-сборка с bundle ID `.liquidglassqa` открыла `NavigationSplitView`; в accessibility-дереве и реальном окне видны обе основные секции и Search detail. Library переключилась без пустой области, пустое состояние осталось центрировано, стандартная кнопка скрытия sidebar доступна. Проверена системная Settings scene из toolbar.
- Debug и Release arm64 сборки `xcodebuild` завершились успешно с target `arm64-apple-macos14.0`; минимальная версия проекта осталась macOS 14. Отдельная Release копия приложения прошла `codesign --verify --deep --strict` и запускалась для реального UI QA.
- `.venv/bin/ruff check .` прошёл; `.venv/bin/pytest --ignore=tests/test_switch.py` — **31 passed**. Полный `.venv/bin/pytest` аварийно завершил Python при создании Qt `QApplication` в `tests/test_switch.py`; macOS показала системный диалог «Приложение Python неожиданно завершило работу». Это локальный сбой Qt Cocoa/platform plugin; SwiftUI приложение запускается отдельно. Qt/Python реализация не менялась.
- GitHub CI PR run [40126927774](https://github.com/gregkorneev-BMSTU/study-agent/actions/runs/40126927774): jobs Python 3.12 и 3.13 упали в `tests/test_ocr_model.py`, потому что тест импортирует `tqdm.auto`, а workflow устанавливает только `.[dev]`, без optional OCR extra; Ruff после этого не запускался. Это обнаруженная, но не изменённая здесь проблема окружения/тестовой зависимости вне macOS UI.
- `NavigationSplitView` компилируется с deployment target macOS 14; минимальная версия в проекте не повышалась. Фактический запуск проверялся только на macOS 27, не на macOS 14/15.
- Сравнительные исходники Beta 2 лежат в `../artifacts/macos-liquid-glass-qa/before/`; они происходят из нативных macOS screenshot в `artifacts/readme/`. Реальные Release captures Search, Library и Settings в светлой и тёмной темах находятся в `../artifacts/macos-liquid-glass-qa/after/` и представлены в [отчёте](../artifacts/macos-liquid-glass-qa/README.md). Qt скриншоты `liquid-glass-qa` не использовались как доказательство поведения SwiftUI.
- UI Automation/XCTest target в проекте отсутствует; переключение выполнено вручную в реальном приложении. VoiceOver-проход, системный Reduce Transparency, системный Reduce Motion, изменение Accent Color и испытания на macOS 14 физически не запускались. Доступность и системные цвета поддерживаются штатными SwiftUI компонентами; API `accessibilityReduceMotion` и `colorSchemeContrast` доступны на deployment target.
- CPU/RAM/FPS до и после не измерялись; численные показатели не заявляются. В интерфейс не добавлялись собственный blur, GPU pipeline, timer или непрерывная анимация.

## Welcome Experience и исправление CI — 2026-10-24

- Xcode Debug и Release для SDK 27 собраны с deployment target macOS 14. QA копия Release запускалась с отдельным bundle ID, поэтому установки и настройки пользователя не затрагивались.
- Реально проверены страницы знакомства 1→2→3, переход к шагу 1/5 старого SetupWizard и переход к диагностике 2/5 в той же панели. Русская локаль на светлой теме подтвердила двуязычный текст и подпись прогресса. Второй sheet не возник.
- На первом запуске скриншот и accessibility tree показали, что код AppKit обновляет `NSMenuItem.title` для верхних меню согласно сохранённому языку. Snapshot CUA всё ещё сообщал английские accessibility-названия этих верхних пунктов после изменения `NSMenuItem.title`, поэтому доступность меню требует отдельной перепроверки на разблокированном рабочем столе.
- Снимки CUA просмотрены во время реального запуска, но не добавлены в репозиторий: системный захват экрана сохранял lock screen macOS. Не использовать эти неверные файлы; ограничения записаны в [отчёте QA](../artifacts/macos-onboarding-qa/README.md).
- В CI root cause повторных падений был `ModuleNotFoundError: tqdm` в `tests/test_ocr_model.py`, где тестируется progress wrapper Chandra, но workflow ставит `.[dev]`. `tqdm>=4.66,<5` добавлен к dev extra; OCR weights и полный OCR extra остаются вне обычного CI. GitHub Actions run `40128761613` прошёл полную матрицу Python 3.12/3.13, включая pytest и Ruff.
- `.venv/bin/pytest --ignore=tests/test_switch.py`: 31 passed; `.venv/bin/ruff check .`: All checks passed. Полный локальный pytest по-прежнему ограничен аварией Qt Cocoa plugin в `tests/test_switch.py`. Реальная диагностика в Xcode-only QA build показывает backend недоступным, поскольку такой сборкой helper не упаковывался; packaging builder отдельно не прогонялся в этой задаче.
- macOS 14/15, VoiceOver, системный Reduce Motion, полный клавиатурный прогон, performance и реальные сценарии завершения/миграции не проверялись.

## Будущая стратегия

- Быстрые unit-тесты для извлечения текста, нормализации метаданных, разбиения и маршрутизации без внешних моделей.
- Лёгкие фикстуры синтетических документов в tests; не хранить пользовательские учебные материалы в Git.
- Smoke-тест клонирования/установки на чистой машине: приложение не должно ожидать путь автора, его `.venv`, модели или локальную конфигурацию.
- Проверять расположение БД, кэша и логов вне репозитория и отсутствие их в `git status`.
- Платформенные проверки файловых диалогов, путей с пробелами/Unicode, прав доступа и открытия источника на Windows/macOS.
- OCR и LLM проверять отдельными opt-in интеграционными тестами на выбранных разрешённых материалах; базовый CI не загружает модель и не отправляет документы в сеть.
- Отдельная маркировка/команда для интеграционных тестов с реальными локальными моделями и файловыми индексами.
- Проверять воспроизводимость ссылок на источники, повторную индексацию, удаление источника и обработку недоступных путей.
- Не требовать сетевого доступа или Ollama в стандартном CI.

## Результат первого запуска

Проверки 2026-10-22: после установки Homebrew Python 3.12.15 и создания `.venv` команда установки `.[dev]` прошла; `pytest` — 5 passed; `ruff check .` — All checks passed. Проверены фильтр `.txt`/`.md`, чтение UTF-8, отказ для traversal и символьных ссылок. Для локального запуска pytest добавляет `src/` через конфигурацию; README использует обычную установку пакета вместо editable `.pth`. GitHub Actions успешно выполнил установку, pytest и Ruff для Python 3.12 и 3.13; используются actions на Node.js 24 и фиксированный `ubuntu-24.04` runner.

Проверки OCR-изменений 2026-10-24: `ruff check .` прошёл; `pytest --ignore=tests/test_switch.py` — 25 passed. Полный `pytest` по-прежнему аварийно завершает Python при создании Qt `minimal` application в `tests/test_switch.py` на локальном PySide6 plugin loader. В тестах OCR используется синтетическая подмена PDFium/Chandra; модельные веса не загружались.

Панель About 2026-10-24: Release target Xcode собрался под arm64; в сгенерированном `Info.plist` проверены `CFBundleShortVersionString=0.1.0`, `CFBundleVersion=1`, `NSHumanReadableCopyright=Developer: Gregory Korneev`, `CFBundleIconName=AppIcon` и `CFBundleIconFile=AppIcon`. Весы/модели для этой проверки не использовались.

Настройки macOS 2026-10-24: удалено ручное поле тега Ollama, оставлен список установленных моделей. `xcodebuild` Debug arm64 — успешно; `ruff check .` — успешно; `pytest --ignore=tests/test_switch.py` — 25 passed. Полный `pytest` повторно аварийно завершился в известном `tests/test_switch.py` при создании Qt `minimal` application.

Настройки прозрачности macOS 2026-10-24: переключатель удалён, а toolbar использует автоматический системный фон. `xcodebuild` Debug arm64 — успешно; `ruff check .` — успешно; `pytest --ignore=tests/test_switch.py` — 25 passed.

Dock-иконка macOS 2026-10-24: удалено ручное назначение 1024×1024 PNG через `NSApplication.applicationIconImage`; размер берётся из Xcode `AppIcon` asset catalog. Release arm64 `xcodebuild` — успешно.


## Проверка v1 Beta 2 — 2026-10-24

- `.venv`-сборка полного `pytest` один раз завершилась с Qt Cocoa abort в `tests/test_switch.py` во время параллельной упаковки. Повторный полный запуск в изолированном Python 3.12 окружении с проектными зависимостями: **34 passed**; `ruff check .`: **All checks passed**.
- `scripts/build_macos_dmg.sh --mode development --suffix beta.2` собрал Xcode Release, arm64 Python helper с OCR runtime и DMG. В `Info.plist`: версия `1.0.0`, build `2`. Размер DMG — 227,682,996 bytes. `hdiutil verify` подтвердил целостность; корень образа содержит приложение, `Applications → /Applications` и `.DS_Store`.
- `codesign --verify --deep --strict` подтвердил подпись смонтированного `.app`; SwiftUI-приложение из образа запускалось в локальной проверке. Визуально проверено центрирование пустого состояния библиотеки. Helper `diagnose_backend` вернул `backend_healthy=true`, `pdf_available=true`, `ocr_runtime_available=true`, `ocr_weights_state=missing`. Веса Chandra не скачивались, OCR inference не запускался.
- SHA-256 `StudyAgent-v1.0.0-beta.2-macos-arm64.dmg`: `8a6d47363f04d43f326a4501b92996ecde3fc19db1e168a940f8aff7c0feb2f2`. Это ad-hoc сборка без Developer ID и нотариализации; Gatekeeper и чистая установка на другом Mac не проверялись.

## Проверка v1 Beta 3 — 2026-10-25

- GitHub Actions run [40133808873](https://github.com/gregkorneev-BMSTU/study-agent/actions/runs/40133808873) завершился успешно: Python 3.12/3.13, полный `pytest` и Ruff. Локальный `.venv/bin/python -m ruff check .` прошёл; `.venv/bin/python -m pytest -q --ignore=tests/test_switch.py` — **31 passed**. Полный локальный pytest завершил Python с `Fatal Python error: Aborted` при создании Cocoa `QApplication` в `tests/test_switch.py`.
- Xcode Debug и Release arm64 собраны на macOS 27 SDK с deployment target 14.0. Swift compiler выдал предупреждение о `BackendProcessControl` без `Sendable`; сборки завершились успешно. macOS 14/15 не проверялись.
- 25.10.2026 приложение заново собрано скриптом `scripts/build_macos_native_app.sh` в `/tmp/study-agent-liquid-glass-build` и запущено из этой копии. В Settings через accessibility tree и реальный скриншот проверено: отдельной секции/плашки Liquid Glass нет; системные группы настроек и controls отображаются штатно. Запущенная версия — Beta 3 build 3; исходники не добавляют собственный параметр прозрачности окна.
- DMG `StudyAgent-v1.0.0-beta.3-macos-arm64.dmg`: **228,131,619 bytes**, версия Info.plist `1.0.0 (3)`, `hdiutil verify` — VALID. Образ содержит приложение, символьную ссылку `Applications → /Applications` и `.DS_Store`.
- На смонтированном HFS+ DMG строгий `codesign --verify --deep --strict` сообщил о FinderInfo xattrs на вложенных лицензионных файлах. После копирования приложения в отдельную папку с `ditto --noextattr --norsrc` строгая проверка подписи прошла. Это не проверка Gatekeeper или Finder drag-install на чистом Mac.
- Встроенный helper ответил на `diagnose_backend`: backend и PDF доступны, `ocr_runtime_available=true`, `ocr_weights_state=missing`. Веса Chandra не скачивались; OCR inference не запускался.
- Реальные скриншоты Release app сохранены в `../artifacts/readme/`: поиск и библиотека тёмной темы, настройки тёмной и светлой темы. При проверке русскоязычного интерфейса системные заголовки верхнего меню оставались на английском языке macOS; синхронизация заголовков меню с языком приложения требует исправления.
- Использование CPU/RAM/FPS, VoiceOver, полного keyboard-only взаимодействия, Reduce Transparency, чистая установка и Gatekeeper на другом компьютере не проверялись. Не заявлять измеренные FPS или совместимость, не проверенную физически.

## SA-01: воспроизводимый замер TXT

На macOS в локальном `.venv` создан временный корпус из 30 синтетических TXT, каждый с 80 повторениями фразы. SQLite размещалась в том же временном каталоге; веса OCR не загружались. Один прогон `DocumentIndexer.sync_source` и `search_sources` через `perf_counter` дал: первая индексация 0,0464 с и 30 извлечений; повторная 0,0125 с и 0 извлечений; после изменения одного файла 0,0333 с и 1 извлечение; поиск 0,0009 с и 0 извлечений (8 результатов по лимиту). Это локальные ориентиры, не пороги производительности для PDF/OCR или других машин.

Проверка реализации SA-01 на macOS (2026-10-25): `.venv/bin/python -m pytest -q --ignore=tests/test_switch.py` — **58 passed**; `.venv/bin/ruff check .` — успешно. Полный `pytest -q` аварийно завершился при создании Qt Cocoa `QApplication` в `tests/test_switch.py`; это не считается успешным полным прогоном. Xcode Release `xcodebuild` с `CODE_SIGNING_ALLOWED=NO` прошёл после исправления захвата `self`; остаётся прежнее предупреждение Swift 6 о `BackendProcessControl` как non-Sendable. JSON Lines smoke test с временной SQLite подтвердил поток прогресса, финальный отчёт и поиск по кириллическому имени; Windows-сборка на этой машине не проверялась.

## Дополнительная проверка PR #11 перед объединением

Регрессии проверяют: `search.result.indexing` до и во время первой индексации, успешный поиск после завершения; занятую файловую блокировку (`index_busy`) и повтор команды после её освобождения; ошибки `stat()` и исчезновение отдельного файла при сохранении старого текста и обработке остальных; отключение FTS5, запись в основной `chunks`, последующее восстановление FTS5 с перестройкой индекса и триггеров. macOS-очередь проверена компиляцией Release и просмотром последовательного worker; отдельного UI automation теста очереди нет.

Локально `.venv/bin/python -m pytest -q --ignore=tests/test_switch.py` — **64 passed**, `.venv/bin/ruff check .` — успешно, Xcode Release с `CODE_SIGNING_ALLOWED=NO` — успешно. Полный `pytest -q` по-прежнему аварийно завершает Python в Qt Cocoa fixture `tests/test_switch.py`, поэтому успех полного локального набора не заявляется. GitHub Actions проверяется отдельно для обновлённого коммита PR.

## SA-04 — native indexing UI

- Xcode Debug и Release сборки с `CODE_SIGNING_ALLOWED=NO` прошли для текущих изменений на macOS 27 SDK и deployment target macOS 14.
- `.venv/bin/python -m pytest -q --ignore=tests/test_switch.py`: **70 passed**. Полный локальный pytest аварийно завершился в `tests/test_switch.py` при создании Cocoa `QApplication`; это известное ограничение Qt platform plugin, полный локальный набор не считается прошедшим.
- `.venv/bin/ruff check .`: успешно.
- `swiftc` harness `tests/macos_client/model_queue.swift` прошёл: проверены декодирование page/heading/chunk metadata, разные IDs нескольких фрагментов одного PDF и повтор неудачной операции библиотеки. Swift compiler повторяет существующее предупреждение о `BackendProcessControl` без `Sendable`.
- Ручная CUA-проверка отдельной копии `.app` с изолированным bundle ID и синтетическим bridge подтвердила пустую библиотеку, строку источника (2 документа/3 фрагмента), локальный ответ, два использованных фрагмента и отображение PDF-страниц 17/18. Progress-команды проверены Swift harness; длительный экранный прогресс и отмена в живом окне не подтверждались. VoiceOver, macOS 14, отключение диска во время синхронизации и реальный переход PDF viewer на страницу не проверялись.
- CUA показал настоящие окна, однако screenshot tool не предоставляет способ сохранить полученные изображения в рабочий каталог; вместо скриншотов зафиксированы сценарии и это ограничение в [QA README](../artifacts/sa-04-swiftui-qa/README.md). Не добавлялись сгенерированные или подменённые скриншоты.

### Финальное ревью SA-04

- Production `mac_bridge.dispatch` с настоящими `DocumentIndexer`, extractors и отдельной временной SQLite обработал синтетическую временную папку TXT/PDF/DOCX: первично 3 документа; после изменения TXT и PDF и удаления DOCX — 2 повторно обработанных, 1 удалённый. Поиск подтвердил новые/удалённые совпадения и вернул страницу PDF 1 и заголовок раздела DOCX. PDF имел текстовый слой выше порога OCR, веса не загружались и OCR inference не выполнялся.
- Python tests проверяют восстановление сохранённой ошибки при новом `index_status`; Swift harness проверяет issue DTO, технический code отдельно от отображаемого описания и запрет смены состояния после `.cancelling`/`.cancelled`.
- В изолированной копии приложения визуально осмотрены Settings в светлой и тёмной теме; обе отображаются. В Library показана строка источника с восстановленным предупреждением из `index_status.issues`. Пользовательские настройки основного приложения не менялись.
- Проверку малого окна и запуск живой backend error/cancel из меню не удалось закончить: CUA перестал доставлять клики в окно (`noWindowsAvailable`/ScreenCaptureKit `-3811`). VoiceOver и macOS 14 не проверялись.
- `.venv/bin/python -m pytest -q --ignore=tests/test_switch.py` — **71 passed**; `ruff check .` — успешно; полный `pytest -q` аварийно завершился при создании Cocoa `QApplication` в `tests/test_switch.py`. Xcode Debug/Release и Swift queue harness прошли; сборки сохраняют предупреждение о `BackendProcessControl` без `Sendable`.

## Проверка выпуска v1 Beta 4 — 2026-10-25

- Версии проверены в упакованном Info.plist: `CFBundleShortVersionString=1.0.0`, `CFBundleVersion=4`. Swift-приложение и PyInstaller backend содержат arm64.
- `scripts/build_macos_dmg.sh --mode development --suffix beta.4` завершился успешно. DMG содержит `Study Agent.app`, `Applications → /Applications` и `.DS_Store`; размер **233,938,263 байта**. `hdiutil verify` вернул `VALID`.
- После копирования приложения из образа удалены FinderInfo extended attributes; `codesign --verify --deep --strict` прошёл. Это ad-hoc подпись без Developer ID и нотариализации.
- Упакованный backend ответил на `diagnose_backend`: backend и PDF runtime доступны, Chandra runtime присутствует. Весов и OCR inference в составе выпуска нет.
- SHA-256 `StudyAgent-v1.0.0-beta.4-macos-arm64.dmg`: `90a2108d804d5b8da8f5fc6168100ee2e9023781def9d85b6303ef5f71c143f5`.
- `.venv/bin/python -m pytest -q --ignore=tests/test_switch.py` — **71 passed**; `.venv/bin/ruff check .` — успешно; Xcode Release arm64 build завершился в составе сборки DMG. Полный локальный pytest не запускался повторно: известен abort на Cocoa `QApplication` в `tests/test_switch.py`; CI PR #12 прошёл для Python 3.12/3.13 и macOS client.

## SA-03: первые три шага — 2026-10-26

Ветка `feature/sa-03-rag`: `.venv` создана на Python 3.12 из `.[dev]`; `.venv/bin/python -m pytest -q` — **102 passed**, `.venv/bin/python -m ruff check .` — **All checks passed**. Полный pytest включает Qt switch-тесты; в этом свежем окружении прежний Qt abort не воспроизвёлся. `git diff --check` прошёл.

Новые проверки используют только временные синтетические данные и mock embedding runtime: Markdown heading paths и line markers, Setext, code fences/indented code, сохранение помещающихся таблиц/кода и жёсткие лимиты, optional token counter; batch/query API и `truncate=false`; отклонение неверных/NaN/нулевых векторов; запрет remote models, HTTP proxies и redirects; отсутствие автоматической загрузки; смена digest; миграция v1 → v2 с сохранением FTS; перезапуск, пересчёт изменённого текста/heading, независимые профили и источники, cascade delete, изменение текста во время inference, ошибка batch, отмена и продолжение.

Дополнительный сквозной Python-прогон `extractors → DocumentIndexer → SQLite → EmbeddingIndexer` на временной русскоязычной Markdown-папке с синтетическим эмбеддером: один документ, два фрагмента/вектора; после открытия новым `IndexStorage` — два skipped; `PRAGMA user_version=2`, `integrity_check=ok`, `foreign_key_check` без ошибок.

Веса моделей не скачивались; реальный `/api/embed`, качество/скорость/память embedding-моделей и Windows не проверялись. UI/bridge не менялись, Xcode build для этого backend-изменения не запускался. Векторный/гибридный поиск и новый RAG не входят в эту часть; Issue #3 остаётся открытым.

## SA-03: поиск через приложение — 2026-10-26

После интеграции retrieval/RAG/SwiftUI/PySide6 полный pytest — **137 passed**, Ruff — успешно. Новые проверки покрывают смысловой запрос без совпадающих слов, RRF, source isolation, stale/missing vectors, отсутствие document embedding при поиске, отказ без вызова LLM, поддельные клиентские hits, invalid citations/URL, перенумерацию только процитированных источников, независимость текстового индекса от отсутствующей embedding-модели и сохранение найденных фрагментов при отказе RAG. CI не запускался: по указанию пользователя коммиты только локальные.

С явного разрешения скачана `qwen3-embedding:0.6b`. На синтетическом корпусе 8 документов/10 запросов измерены lexical/semantic/hybrid; проверены повторное открытие SQLite и реальный ответ `gemma4:e2b`, включая запрос вне корпуса. Xcode Debug/Release, Swift harness и PyInstaller app build прошли. CUA подтвердила реальную Library (16/16 vectors) и выдачу с matrix.md первым, но native pipe закрылся до осмотра окончательного ответа. Отдельно финальный упакованный helper вернул grounded answer с единственным источником matrix.md. Полные измерения, ограничения UI-проверки и воспроизводимые JSON: [QA SA-03](../artifacts/sa-03-search-qa/README.md).
