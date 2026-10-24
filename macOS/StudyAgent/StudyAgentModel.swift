import AppKit
import Combine
import Foundation
import SwiftUI

enum MainSection: String, CaseIterable, Identifiable {
    case search
    case library
    case settings

    var id: Self { self }

    func title(language: AppLanguage) -> String {
        switch self {
        case .search: L10n.text("Поиск", language: language)
        case .library: L10n.text("Библиотека", language: language)
        case .settings: L10n.text("Настройки", language: language)
        }
    }

    var symbol: String {
        switch self {
        case .search: "magnifyingglass"
        case .library: "books.vertical"
        case .settings: "gearshape"
        }
    }
}

enum AppTheme: String, CaseIterable, Identifiable {
    case system
    case light
    case dark

    var id: Self { self }

    func title(language: AppLanguage) -> String {
        switch self {
        case .system: L10n.text("Как в системе", language: language)
        case .light: L10n.text("Светлая", language: language)
        case .dark: L10n.text("Тёмная", language: language)
        }
    }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: nil
        case .light: .light
        case .dark: .dark
        }
    }
}

struct SavedFolder: Codable, Identifiable, Hashable {
    var id: UUID
    var name: String
    var bookmark: Data
}

struct SourceSummary: Identifiable, Decodable {
    var id: String { path }
    let name: String
    let path: String
    let documentCount: Int

    enum CodingKeys: String, CodingKey {
        case name, path
        case documentCount = "document_count"
    }
}

struct SearchHit: Identifiable, Decodable {
    var id: String { "\(sourceRoot)/\(documentID)" }
    let title: String
    let documentID: String
    let excerpt: String
    let score: Int
    let sourceRoot: String

    enum CodingKeys: String, CodingKey {
        case title, excerpt, score
        case documentID = "document_id"
        case sourceRoot = "source_root"
    }
}

@MainActor
final class StudyAgentModel: ObservableObject {
    @Published var selectedSection: MainSection = .search
    @Published var isImportingFolders = false
    @Published var query = ""
    @Published var isSearching = false
    @Published var searchStatus = "Выберите папку в разделе «Библиотека», чтобы начать поиск."
    @Published var hits: [SearchHit] = []
    @Published var answerText: String?
    @Published var sourceSummaries: [SourceSummary] = []
    @Published var modelNames: [String] = []
    @Published var modelName: String {
        didSet { defaults.set(modelName, forKey: Keys.model) }
    }
    @Published var modelStatus = "Список моделей загружается с локального Ollama."
    @Published var ollamaStatus = "Проверка Ollama…"
    @Published var language: AppLanguage {
        didSet {
            defaults.set(language.rawValue, forKey: Keys.language)
            refreshSources()
            refreshModels()
        }
    }
    @Published var theme: AppTheme {
        didSet { defaults.set(theme.rawValue, forKey: Keys.theme) }
    }
    @Published var highContrast: Bool {
        didSet { defaults.set(highContrast, forKey: Keys.highContrast) }
    }
    @Published var reduceMotion: Bool {
        didSet { defaults.set(reduceMotion, forKey: Keys.reduceMotion) }
    }
    @Published private(set) var folders: [SavedFolder] = []
    @Published var showingSetup = false

    private let defaults = UserDefaults.standard
    private let bridge = MacBackendClient()
    private var didPromptSetupThisLaunch = false

    init() {
        Self.migrateLegacyPreferences(into: .standard)
        language = defaults.string(forKey: Keys.language)
            .flatMap(AppLanguage.init(rawValue:)) ?? .systemDefault
        let savedTheme = defaults.string(forKey: Keys.theme).flatMap(AppTheme.init(rawValue:))
        theme = savedTheme ?? .system
        modelName = defaults.string(forKey: Keys.model) ?? "qwen3.5:4b"
        highContrast = defaults.bool(forKey: Keys.highContrast)
        reduceMotion = defaults.bool(forKey: Keys.reduceMotion)
        folders = Self.decodeFolders(from: defaults.data(forKey: Keys.folders))
    }

    func text(_ source: String) -> String {
        L10n.text(source, language: language)
    }

    var setupCompleted: Bool {
        defaults.bool(forKey: "setup.completed.v1")
    }

    func presentSetupIfNeeded() {
        guard !setupCompleted, !didPromptSetupThisLaunch else { return }
        didPromptSetupThisLaunch = true
        showingSetup = true
    }

    func finishSetup() {
        defaults.set(true, forKey: "setup.completed.v1")
        showingSetup = false
        refreshModels()
    }

    func diagnoseBackend() async throws -> [String: Any] {
        try await bridge.request(command: "diagnose_backend")
    }

    func installOCRModel(progress: @escaping ([String: Any]) -> Void) async throws -> [String: Any] {
        try await bridge.requestStreaming(command: "install_ocr_model", progress: progress)
    }

    func addFolders(_ urls: [URL]) {
        var added = 0
        for url in urls {
            let accessGranted = url.startAccessingSecurityScopedResource()
            defer {
                if accessGranted { url.stopAccessingSecurityScopedResource() }
            }
            do {
                let bookmark = try url.bookmarkData(
                    options: [],
                    includingResourceValuesForKeys: nil,
                    relativeTo: nil
                )
                guard !folders.contains(where: { $0.name == url.lastPathComponent && Self.sameFolder($0, url) }) else {
                    continue
                }
                folders.append(SavedFolder(id: UUID(), name: url.lastPathComponent, bookmark: bookmark))
                added += 1
            } catch {
                searchStatus = L10n.format(
                    "Не удалось сохранить доступ к папке «%@»: %@",
                    language: language,
                    url.lastPathComponent,
                    localizedError(error)
                )
            }
        }
        saveFolders()
        if added > 0 {
            selectedSection = .library
            refreshSources()
        }
    }

    func removeFolder(_ folder: SavedFolder) {
        folders.removeAll { $0.id == folder.id }
        saveFolders()
        refreshSources()
    }

    func removeFolder(at path: String) {
        folders.removeAll { Self.path(of: $0) == path }
        saveFolders()
        refreshSources()
    }

    func refreshSources() {
        Task {
            do {
                let (urls, opened) = try openFolderURLs()
                defer { closeFolderURLs(urls, opened: opened) }
                let response = try await bridge.request(command: "list_sources", fields: [
                    "roots": urls.map(\.path)
                ])
                sourceSummaries = try response.decode("sources", as: [SourceSummary].self)
                searchStatus = sourceSummaries.isEmpty
                    ? text("Добавьте папку с учебными материалами в библиотеку.")
                    : L10n.format("Подключено источников: %d.", language: language, sourceSummaries.count)
            } catch {
                sourceSummaries = []
                searchStatus = localizedError(error)
            }
        }
    }

    func refreshModels() {
        modelStatus = text("Подключение к локальному Ollama…")
        Task {
            do {
                let response = try await bridge.request(command: "list_models")
                modelNames = try response.decode("models", as: [String].self)
                modelStatus = modelNames.isEmpty
                    ? text("В Ollama пока нет установленных моделей.")
                    : L10n.format("Найдено моделей: %d.", language: language, modelNames.count)
                ollamaStatus = text("Ollama подключена")
            } catch {
                modelNames = []
                modelStatus = localizedError(error)
                ollamaStatus = text("Ollama не отвечает")
            }
        }
    }

    func saveModel() {
        let trimmed = modelName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            modelStatus = text("Укажите тег модели Ollama.")
            return
        }
        modelName = trimmed
        modelStatus = L10n.format("Модель «%@» сохранена на этом компьютере.", language: language, trimmed)
    }

    func search() {
        let searchText = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !searchText.isEmpty else {
            searchStatus = text("Введите тему или вопрос для поиска.")
            hits = []
            answerText = nil
            return
        }
        guard !folders.isEmpty else {
            searchStatus = text("Сначала подключите папку в разделе «Библиотека».")
            return
        }

        isSearching = true
        hits = []
        answerText = nil
        searchStatus = text("Ищу в подключённых материалах…")
        Task {
            do {
                let (urls, opened) = try openFolderURLs()
                defer { closeFolderURLs(urls, opened: opened) }
                let searchResponse = try await bridge.request(command: "search", fields: [
                    "roots": urls.map(\.path),
                    "query": searchText
                ])
                let found = try searchResponse.decode("hits", as: [SearchHit].self)
                hits = found
                guard !found.isEmpty else {
                    searchStatus = text("В выбранных материалах не нашёл фрагментов по этому запросу.")
                    isSearching = false
                    return
                }
                searchStatus = L10n.format("Нашёл %d фрагментов. Формирую ответ локально…", language: language, found.count)
                let hitValues: [[String: Any]] = found.map { hit in
                    [
                        "title": hit.title,
                        "document_id": hit.documentID,
                        "excerpt": hit.excerpt,
                        "score": hit.score,
                        "source_root": hit.sourceRoot
                    ]
                }
                let answerResponse = try await bridge.request(command: "answer", fields: [
                    "model": modelName,
                    "query": searchText,
                    "hits": hitValues,
                    "language": language.rawValue
                ])
                answerText = try answerResponse.decode("answer", as: String.self)
                searchStatus = L10n.format(
                    "Ответ подготовлен локально по %d источникам.",
                    language: language,
                    min(found.count, 5)
                )
            } catch {
                searchStatus = localizedError(error)
            }
            isSearching = false
        }
    }

    func open(_ hit: SearchHit) {
        guard let folder = folders.first(where: { Self.path(of: $0) == hit.sourceRoot }) else {
            searchStatus = text("Источник больше не подключён.")
            return
        }
        do {
            let (urls, opened) = try openFolderURLs(for: [folder])
            defer { closeFolderURLs(urls, opened: opened) }
            guard let root = urls.first else { return }
            let fileURL = root.appending(path: hit.documentID).standardizedFileURL
            guard fileURL.path.hasPrefix(root.path + "/"), FileManager.default.fileExists(atPath: fileURL.path) else {
                searchStatus = text("Не удалось открыть исходный файл.")
                return
            }
            NSWorkspace.shared.open(fileURL)
        } catch {
            searchStatus = localizedError(error)
        }
    }

    private func localizedError(_ error: Error) -> String {
        L10n.text(error.localizedDescription, language: language)
    }

    private func saveFolders() {
        guard let data = try? JSONEncoder().encode(folders) else { return }
        defaults.set(data, forKey: Keys.folders)
    }

    private func openFolderURLs(for selected: [SavedFolder]? = nil) throws -> ([URL], [Bool]) {
        var urls: [URL] = []
        var opened: [Bool] = []
        for folder in selected ?? folders {
            var stale = false
            let url = try URL(
                resolvingBookmarkData: folder.bookmark,
                options: [],
                relativeTo: nil,
                bookmarkDataIsStale: &stale
            )
            let hasAccess = url.startAccessingSecurityScopedResource()
            urls.append(url)
            opened.append(hasAccess)
            if stale, let updated = try? url.bookmarkData(options: []) {
                updateBookmark(updated, for: folder.id)
            }
        }
        return (urls, opened)
    }

    private func closeFolderURLs(_ urls: [URL], opened: [Bool]) {
        for (url, hasAccess) in zip(urls, opened) where hasAccess {
            url.stopAccessingSecurityScopedResource()
        }
    }

    private func updateBookmark(_ bookmark: Data, for id: UUID) {
        guard let index = folders.firstIndex(where: { $0.id == id }) else { return }
        folders[index].bookmark = bookmark
        saveFolders()
    }

    private static func sameFolder(_ folder: SavedFolder, _ url: URL) -> Bool {
        var stale = false
        guard let existing = try? URL(
            resolvingBookmarkData: folder.bookmark,
            options: [],
            relativeTo: nil,
            bookmarkDataIsStale: &stale
        ) else { return false }
        return existing.standardizedFileURL == url.standardizedFileURL
    }

    private static func path(of folder: SavedFolder) -> String? {
        var stale = false
        return try? URL(
            resolvingBookmarkData: folder.bookmark,
            options: [],
            relativeTo: nil,
            bookmarkDataIsStale: &stale
        ).path
    }

    private static func decodeFolders(from data: Data?) -> [SavedFolder] {
        guard let data else { return [] }
        return (try? JSONDecoder().decode([SavedFolder].self, from: data)) ?? []
    }

    private static func migrateLegacyPreferences(into defaults: UserDefaults) {
        guard !defaults.bool(forKey: Keys.migrated) else { return }
        let legacy = UserDefaults(suiteName: "com.StudyAgent.StudyAgent")
        if defaults.string(forKey: Keys.model) == nil,
           let model = legacy?.string(forKey: "model") {
            defaults.set(model, forKey: Keys.model)
        }
        for key in [Keys.theme, Keys.highContrast, Keys.reduceMotion] {
            if defaults.object(forKey: key) == nil, let value = legacy?.object(forKey: key) {
                defaults.set(value, forKey: key)
            }
        }
        if defaults.data(forKey: Keys.folders) == nil,
           let oldPaths = legacy?.stringArray(forKey: "sources") {
            let folders = oldPaths.compactMap { path -> SavedFolder? in
                let url = URL(filePath: path)
                guard url.hasDirectoryPath, let bookmark = try? url.bookmarkData(options: []) else {
                    return nil
                }
                return SavedFolder(id: UUID(), name: url.lastPathComponent, bookmark: bookmark)
            }
            if let data = try? JSONEncoder().encode(folders) {
                defaults.set(data, forKey: Keys.folders)
            }
        }
        defaults.set(true, forKey: Keys.migrated)
    }
}

private enum Keys {
    static let folders = "library.bookmarks.v1"
    static let model = "model"
    static let language = "general/language"
    static let theme = "appearance/theme"
    static let highContrast = "appearance/high_contrast"
    static let reduceMotion = "appearance/reduce_motion"
    static let migrated = "migration.fromQt.v1"
}

private struct MacBackendClient {
    func request(command: String, fields: [String: Any] = [:]) async throws -> [String: Any] {
        var request = fields
        request["command"] = command
        request["request_id"] = UUID().uuidString
        let requestData = try JSONSerialization.data(withJSONObject: request, options: [.fragmentsAllowed])
        return try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    let executable = try Self.executableURL()
                    let process = Process()
                    let input = Pipe()
                    let output = Pipe()
                    process.executableURL = executable
                    process.standardInput = input
                    process.standardOutput = output
                    process.standardError = FileHandle.nullDevice
                    try process.run()
                    input.fileHandleForWriting.write(requestData + Data([0x0A]))
                    try input.fileHandleForWriting.close()
                    let responseData = output.fileHandleForReading.readDataToEndOfFile()
                    process.waitUntilExit()
                    guard process.terminationStatus == 0,
                          let envelope = try JSONSerialization.jsonObject(with: responseData) as? [String: Any] else {
                        throw BackendClientError.invalidResponse
                    }
                    guard envelope["ok"] as? Bool == true,
                          let result = envelope["result"] as? [String: Any] else {
                        let error = envelope["error"] as? [String: Any]
                        throw BackendClientError.message(error?["message"] as? String ?? "Ошибка локального backend.")
                    }
                    continuation.resume(returning: result)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    func requestStreaming(
        command: String,
        fields: [String: Any] = [:],
        progress: @escaping ([String: Any]) -> Void
    ) async throws -> [String: Any] {
        var request = fields
        request["command"] = command
        request["request_id"] = UUID().uuidString
        let requestData = try JSONSerialization.data(withJSONObject: request, options: [.fragmentsAllowed])
        let control = BackendProcessControl()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                DispatchQueue.global(qos: .userInitiated).async {
                    do {
                        let process = Process()
                        let input = Pipe()
                        let output = Pipe()
                        process.executableURL = try Self.executableURL()
                        process.standardInput = input
                        process.standardOutput = output
                        process.standardError = FileHandle.nullDevice
                        control.attach(process)
                        if control.isCancelled { throw CancellationError() }
                        try process.run()
                        input.fileHandleForWriting.write(requestData + Data([0x0A]))
                        try input.fileHandleForWriting.close()

                        var pending = Data()
                        var finalEnvelope: [String: Any]?
                        while true {
                            let chunk = try output.fileHandleForReading.read(upToCount: 16_384) ?? Data()
                            if chunk.isEmpty { break }
                            pending.append(chunk)
                            while let newline = pending.firstRange(of: Data([0x0A])) {
                                let line = Data(pending[..<newline.lowerBound])
                                pending.removeSubrange(..<newline.upperBound)
                                guard let message = try JSONSerialization.jsonObject(with: line) as? [String: Any] else {
                                    continue
                                }
                                if message["event"] as? String == "progress",
                                   let value = message["result"] as? [String: Any] {
                                    DispatchQueue.main.async { progress(value) }
                                } else {
                                    finalEnvelope = message
                                }
                            }
                        }
                        process.waitUntilExit()
                        if control.isCancelled { throw CancellationError() }
                        guard process.terminationStatus == 0, let envelope = finalEnvelope else {
                            throw BackendClientError.invalidResponse
                        }
                        guard envelope["ok"] as? Bool == true,
                              let result = envelope["result"] as? [String: Any] else {
                            let error = envelope["error"] as? [String: Any]
                            throw BackendClientError.message(error?["message"] as? String ?? "Ошибка локального backend.")
                        }
                        continuation.resume(returning: result)
                    } catch {
                        if control.isCancelled {
                            continuation.resume(throwing: CancellationError())
                        } else {
                            continuation.resume(throwing: error)
                        }
                    }
                }
            }
        } onCancel: {
            control.cancel()
        }
    }

    private static func executableURL() throws -> URL {
        let url = Bundle.main.bundleURL
            .appending(path: "Contents/Resources/Backend/StudyAgentBackend/StudyAgentBackend")
        guard FileManager.default.isExecutableFile(atPath: url.path) else {
            throw BackendClientError.missingBackend
        }
        return url
    }
}

private final class BackendProcessControl {
    private let lock = NSLock()
    private var process: Process?
    private var cancelled = false

    var isCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return cancelled
    }

    func attach(_ process: Process) {
        lock.lock()
        self.process = process
        let shouldCancel = cancelled
        lock.unlock()
        if shouldCancel { process.terminate() }
    }

    func cancel() {
        lock.lock()
        cancelled = true
        let runningProcess = process
        lock.unlock()
        if runningProcess?.isRunning == true { runningProcess?.terminate() }
    }
}

private enum BackendClientError: LocalizedError {
    case missingBackend
    case invalidResponse
    case message(String)

    var errorDescription: String? {
        switch self {
        case .missingBackend: "Не найден встроенный локальный backend. Соберите приложение скриптом scripts/build_macos_native_app.sh."
        case .invalidResponse: "Локальный backend вернул некорректный ответ."
        case .message(let message): message
        }
    }
}

private extension Dictionary where Key == String, Value == Any {
    func decode<T: Decodable>(_ key: String, as type: T.Type) throws -> T {
        guard let value = self[key] else { throw BackendClientError.invalidResponse }
        let data = try JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed])
        return try JSONDecoder().decode(type, from: data)
    }
}
