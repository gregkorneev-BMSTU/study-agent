import Foundation

enum AppLanguage: String, CaseIterable, Identifiable {
    case russian = "ru"
    case english = "en"

    static var systemDefault: AppLanguage {
        Locale.current.language.languageCode?.identifier == "ru" ? .russian : .english
    }

    var id: Self { self }

    var displayName: String {
        switch self {
        case .russian: "Русский"
        case .english: "English"
        }
    }
}

enum L10n {
    private static let english: [String: String] = [
        "Поиск": "Search",
        "Библиотека": "Library",
        "Настройки": "Settings",
        "Как в системе": "System",
        "Светлая": "Light",
        "Тёмная": "Dark",
        "Выберите папку в разделе «Библиотека», чтобы начать поиск.": "Choose a folder in Library to start searching.",
        "Список моделей загружается с локального Ollama.": "Loading models from local Ollama…",
        "Проверка Ollama…": "Checking Ollama…",
        "Не удалось сохранить доступ к папке «%@»: %@": "Could not save access to “%@”: %@",
        "Добавьте папку с учебными материалами в библиотеку.": "Add a folder with study materials to your library.",
        "Подключено источников: %d.": "Connected sources: %d.",
        "Подключение к локальному Ollama…": "Connecting to local Ollama…",
        "В Ollama пока нет установленных моделей.": "No models are installed in Ollama yet.",
        "Найдено моделей: %d.": "Models found: %d.",
        "Ollama подключена": "Ollama connected",
        "Ollama не отвечает": "Ollama is not responding",
        "Укажите тег модели Ollama.": "Enter an Ollama model tag.",
        "Модель «%@» сохранена на этом компьютере.": "Model “%@” saved on this computer.",
        "Введите тему или вопрос для поиска.": "Enter a topic or question to search.",
        "Сначала подключите папку в разделе «Библиотека».": "Add a folder in Library first.",
        "Ищу в подключённых материалах…": "Searching connected materials…",
        "В выбранных материалах не нашёл фрагментов по этому запросу.": "No matching passages were found in the selected materials.",
        "Нашёл %d фрагментов. Формирую ответ локально…": "Passages found: %d. Preparing a local answer…",
        "Ответ подготовлен локально по %d источникам.": "Answer prepared locally. Sources: %d.",
        "Источник больше не подключён.": "This source is no longer connected.",
        "Не удалось открыть исходный файл.": "Could not open the source file.",
        "Ошибка локального backend.": "Local backend error.",
        "Не найден встроенный локальный backend. Соберите приложение скриптом scripts/build_macos_native_app.sh.": "The bundled local backend was not found. Build the app with scripts/build_macos_native_app.sh.",
        "Локальный backend вернул некорректный ответ.": "The local backend returned an invalid response.",
        "Открыть Study Agent": "Open Study Agent",
        "Настройки…": "Settings…",
        "Завершить Study Agent": "Quit Study Agent",
        "Добавить папку…": "Add Folder…",
        "Поиск по материалам": "Search Materials",
        "Добавить папку": "Add Folder",
        "Добавить папку с учебными материалами": "Add a folder with study materials",
        "Настройки Study Agent": "Study Agent Settings",
        "Ответы строятся локальной моделью по выбранным источникам.": "Answers are generated locally from your selected sources.",
        "Спросите о лекциях, конспектах или учебниках…": "Ask about lectures, notes, or textbooks…",
        "Вопрос по учебным материалам": "Question about study materials",
        "Спросить": "Ask",
        "Ответ": "Answer",
        "Открыть исходный документ": "Open source document",
        "Подключайте только те папки, которые хотите искать. Файлы не покидают этот компьютер.": "Connect only the folders you want to search. Your files stay on this computer.",
        "Папки пока не добавлены": "No folders added yet",
        "Добавьте папку с PDF, изображениями, Markdown или TXT.": "Add a folder with PDFs, images, Markdown, or TXT files.",
        "%d файлов поддерживаемых форматов": "Supported files: %d",
        "Удалить": "Remove",
        "Отключить папку от библиотеки": "Remove this folder from the library",
        "Локальная языковая модель": "Local Language Model",
        "Установленная модель": "Installed Model",
        "Обновить список моделей": "Refresh Model List",
        "Сохранить модель": "Save Model",
        "Внешний вид и доступность": "Appearance & Accessibility",
        "Цветовая тема": "Color Theme",
        "Повышенный контраст": "Increase Contrast",
        "Уменьшить движение": "Reduce Motion",
        "Конфиденциальность": "Privacy",
        "Поиск выполняется локально. Вопрос и найденные выдержки передаются только в Ollama на этом компьютере.": "Search runs locally. Your question and matching excerpts are sent only to Ollama on this computer.",
        "Обновить модели": "Refresh Models",
        "Изменить язык": "Language",
        "Язык интерфейса": "Interface Language",
        "Русский": "Russian",
        "English": "English",
        "Об Study Agent": "About Study Agent",
        "Локальная библиотека знаний": "Local study library",
        "Ollama: проверка…": "Ollama: checking…",
        "Локальный поиск и анализ учебных материалов.\n\nФайлы остаются на этом компьютере; ответы формируются через Ollama.": "Local search and analysis of study materials.\n\nYour files stay on this computer; answers are generated with Ollama.",
        "Выбранная папка недоступна.": "The selected folder is unavailable.",
        "Нет доступных папок для поиска.": "No folders are available for search.",
        "Вырезать": "Cut",
        "Копировать": "Copy",
        "Вставить": "Paste",
        "Выделить всё": "Select All",
        "Study Agent": "Study Agent",
        "Нет связи с Ollama на этом компьютере. Убедитесь, что приложение запущено.": "Cannot connect to Ollama on this computer. Make sure Ollama is running.",
        "Ollama вернула ответ в неизвестном формате.": "Ollama returned an unrecognized response.",
        "Ollama не отвечает. Откройте приложение Ollama и попробуйте ещё раз.": "Ollama is not responding. Open the Ollama app and try again.",
        "Ollama вернула пустой ответ.": "Ollama returned an empty response.",
        "Unknown backend command": "Unknown backend command",
        "roots must be a list of folder paths": "Roots must be a list of folder paths.",
        "hits must be a list": "Hits must be a list.",
        "each hit must be an object": "Each hit must be an object.",
        "each hit needs source_root, document_id and excerpt strings": "Each hit must include source_root, document_id, and excerpt strings.",
        "request must be a JSON object": "Request must be a JSON object.",
        "model must be a non-empty string": "Model must not be empty.",
        "query must be a non-empty string": "Query must not be empty.",
    ]

    static func text(_ source: String, language: AppLanguage) -> String {
        guard language == .english else { return source }
        return english[source] ?? source
    }

    static func format(_ source: String, language: AppLanguage, _ arguments: CVarArg...) -> String {
        String(
            format: text(source, language: language),
            locale: Locale(identifier: language.rawValue),
            arguments: arguments
        )
    }
}
