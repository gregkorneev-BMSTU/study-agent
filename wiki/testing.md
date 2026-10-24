# Тестирование

## Автоматические проверки

Минимальная CI матрица запускает Python 3.12 и 3.13, `pytest` и `ruff check .`; целевая матрица должна покрывать Windows и macOS, как только зависимости позволяют это надёжно сделать. CI не скачивает модели и не требует Ollama/Chandra weights. Локально запускаются те же команды из README после установки `.[dev]`.

Текущие тесты покрывают `LocalFolderSource`, OCR-маршрутизацию страниц PDF и локальный кэш. Проверки используют подменённый PDF renderer и OCR, не загружают Chandra weights и не проверяют точность модели.

Для v1 Beta 1 добавлены unit-тесты команды `diagnose_backend` в JSON Lines bridge: проверяется формат ответа и определение доступности библиотек без запуска или загрузки весов Chandra. Мастер SwiftUI, системные действия Ollama, загрузка модели и оформление Finder требуют отдельной проверки на реальном Mac. Стандартные Python-тесты не скачивают модели.

Проверка 2026-10-24 перед выпуском: Release arm64 `xcodebuild` прошёл; `ruff check .` прошёл; `pytest --ignore=tests/test_switch.py` — 27 passed. Полный локальный `pytest -q` остановился с `Fatal Python error: Aborted` в `tests/test_switch.py` при создании `QApplication` на текущей macOS/PySide6; это ограничение локальной Qt-проверки, а не результат тестов SwiftUI. GitHub CI ранее падал на Ubuntu при импорте PySide6 из-за отсутствия `libEGL.so.1`; workflow дополнен установкой Qt runtime библиотек, итог нового запуска нужно проверить после push.

Финальный тестовый DMG `StudyAgent-v1.0.0-beta.1-macos-arm64.dmg`: `hdiutil verify` подтвердил checksum образа; при монтировании в корне только `Study Agent.app`, `Applications → /Applications` и скрытая `.DS_Store`; `Info.plist` показывает 1.0.0 (build 1); `codesign --verify --deep --strict` прошёл для ad-hoc подписи; упакованный helper ответил на `diagnose_backend` с доступными PDF/OCR runtime и `ocr_weights_state=unknown`. Приложение скопировано из DMG во временную папку с пробелом в пути и запущено отдельным процессом. Пробный образ в Finder сохранял окно 660 × 380 pt, позиции значков и размер 128 pt. Светлая тема, запуск на чистом Mac, Gatekeeper, нотариализация и фактическая загрузка больших моделей этим прогоном не подтверждены.

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
