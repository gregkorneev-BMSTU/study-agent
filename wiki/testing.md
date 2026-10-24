# Тестирование

## Автоматические проверки

Минимальная CI матрица запускает Python 3.12 и 3.13, `pytest` и `ruff check .`; целевая матрица должна покрывать Windows и macOS, как только зависимости позволяют это надёжно сделать. CI не скачивает модели и не требует Ollama/Chandra weights. Локально запускаются те же команды из README после установки `.[dev]`.

Текущие тесты покрывают `LocalFolderSource`, OCR-маршрутизацию страниц PDF и локальный кэш. Проверки используют подменённый PDF renderer и OCR, не загружают Chandra weights и не проверяют точность модели.

Для v1 Beta 1 добавлены unit-тесты команды `diagnose_backend` в JSON Lines bridge: проверяется формат ответа и определение доступности библиотек без запуска или загрузки весов Chandra. Мастер SwiftUI, системные действия Ollama, загрузка модели и оформление Finder требуют отдельной проверки на реальном Mac. Стандартные Python-тесты не скачивают модели.

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
- В CI root cause повторных падений был `ModuleNotFoundError: tqdm` в `tests/test_ocr_model.py`, где тестируется progress wrapper Chandra, но workflow ставит `.[dev]`. `tqdm>=4.66,<5` добавлен к dev extra; OCR weights и полный OCR extra остаются вне обычного CI. Для GitHub matrix 3.12/3.13 требуется новый run после push.
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
