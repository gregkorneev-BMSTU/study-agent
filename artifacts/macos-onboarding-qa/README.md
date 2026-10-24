# macOS Welcome & Onboarding QA

## Реализация

- Реальный Release `.app` с изолированным bundle ID `com.gregkorneev.studyagent.onboardingqa` запущен на macOS 27.0.1. Accessibility tree и снимок окна подтвердили первый экран на английском в тёмном режиме, переходы на страницы 2 и 3, адаптацию основного действия и переход в существующий `SetupWizard` без второй модальной панели.
- После третьей страницы открываются этапы 1/5 и 2/5 технического мастера. Диагностика показала системные характеристики и ожидаемую ошибку отсутствующего helper: этот smoke build сделан напрямую Xcode и не включает `Contents/Resources/Backend`. Рабочий distribution builder продолжает упаковывать helper.
- Русский язык и светлая тема проверены в том же изолированном `.app`; Accessibility tree подтвердил русские заголовки, описания, кнопки и «Шаг 1 из 3».
- AppKit `NSApp.mainMenu.items` переключает стандартные меню на русский (Файл, Правка, Вид, Окно, Справка) и обратно на английский; имя приложения Study Agent остаётся без перевода. Accessibility tree верхней строки меню сохранил первоначальные названия File/Edit/View/Window/Help после смены `NSMenuItem.title`, поэтому визуальную строку меню нельзя подтвердить тем же UI Automation snapshot.
- Состояние Beta 1/Beta 2 и прерывание процесса до последней страницы проверены по веткам кода; отдельного XCTest target для автоматизации первого запуска в проекте пока нет.

## Сохранённые скриншоты

Экранные кадры Welcome, Library, Private & Local и перехода в SetupWizard были просмотрены через CUA в реальном запущенном приложении. Их невозможно было сохранить в репозиторий: системный `screencapture` захватил заблокированный экран macOS вместо окна приложения. В каталог не включены эти ошибочные кадры; SwiftUI Preview или сгенерированные изображения не выдаются за runtime QA. Повторить архивирование кадров после разблокировки Mac.

## CI failure

Повторяющаяся GitHub Actions ошибка воспроизведена в `tests/test_ocr_model.py`: тестирует обёртку прогресса OCR, которая импортирует `tqdm.auto`, но CI устанавливал только `.[dev]`. В `dev` добавлен лёгкий `tqdm>=4.66,<5`; тяжёлый OCR extra и веса модели в CI не добавляются. GitHub Actions run [40128761613](https://github.com/gregkorneev-BMSTU/study-agent/actions/runs/40128761613) прошёл для Python 3.12 и 3.13: установка dev dependencies, pytest и Ruff успешны в обеих ветках матрицы.

## Проверки и непроверенное

- `xcodebuild` Release и Debug собрали macOS-приложение с deployment target macOS 14 при SDK 27.
- `.venv/bin/pytest --ignore=tests/test_switch.py`: 31 passed; локальный `tests/test_switch.py` ранее аварийно завершал Cocoa Qt plugin в этом Mac окружении.
- `.venv/bin/ruff check .`: All checks passed.
- Нет физической проверки на macOS 14/15, аудита VoiceOver, Reduce Motion и клавиатуры полным циклом. Нельзя заявлять результаты FPS/CPU/RAM: отдельные performance measurements не выполнялись.
