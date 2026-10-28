import AppKit
import Combine
import Foundation
import SwiftUI

enum MainSection: String, CaseIterable, Identifiable {
    case search
    case library

    var id: Self { self }

    func title(language: AppLanguage) -> String {
        switch self {
        case .search: L10n.text("Поиск", language: language)
        case .library: L10n.text("Библиотека", language: language)
        }
    }

    var symbol: String {
        switch self {
        case .search: "magnifyingglass"
        case .library: "books.vertical"
        }
    }
}

enum FirstRunPresentation: String, Identifiable, Equatable {
    case welcome
    case setup

    var id: Self { self }
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

enum SearchMode: String, CaseIterable, Identifiable {
    case lexical, semantic, hybrid
    var id: Self { self }
    func title(language: AppLanguage) -> String {
        switch self {
        case .lexical: L10n.text("По словам", language: language)
        case .semantic: L10n.text("По смыслу", language: language)
        case .hybrid: L10n.text("Гибридный", language: language)
        }
    }
}

struct EmbeddingModel: Decodable, Identifiable {
    var id: String { name }
    let name: String
    let dimensions: Int
}

struct SourceSummary: Identifiable, Decodable {
    var id: String { path }
    let name: String
    let path: String
    let documentCount: Int
    let available: Bool?

    enum CodingKeys: String, CodingKey {
        case name, path
        case documentCount = "document_count", available
    }
}

struct SearchHit: Identifiable, Decodable {
    private let fallbackID = UUID().uuidString
    var id: String { "\(sourceRoot)/\(documentID)/\(chunkID ?? fallbackID)" }
    let title: String
    let documentID: String
    let excerpt: String
    let fullExcerpt: String?
    let matchedExcerpts: [String]?
    var displayExcerpt: String { fullExcerpt ?? excerpt }
    let score: Int
    let sourceRoot: String
    let pageNumber: Int?
    let heading: String?
    let marker: String?
    let extractionType: String?
    let chunkID: String?
    let relatedCount: Int?
    let qualityWarnings: [String]?

    enum CodingKeys: String, CodingKey {
        case title, excerpt, score
        case fullExcerpt = "full_excerpt"
        case matchedExcerpts = "matched_excerpts"
        case documentID = "document_id"
        case sourceRoot = "source_root"
        case pageNumber = "page_number"
        case heading, marker
        case extractionType = "extraction_type"
        case relatedCount = "related_count"
        case qualityWarnings = "quality_warnings"
        case chunkID = "chunk_id"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        title = try values.decode(String.self, forKey: .title)
        documentID = try values.decode(String.self, forKey: .documentID)
        excerpt = try values.decode(String.self, forKey: .excerpt)
        fullExcerpt = try values.decodeIfPresent(String.self, forKey: .fullExcerpt)
        matchedExcerpts = try values.decodeIfPresent([String].self, forKey: .matchedExcerpts)
        score = try values.decode(Int.self, forKey: .score)
        sourceRoot = try values.decode(String.self, forKey: .sourceRoot)
        pageNumber = try values.decodeIfPresent(Int.self, forKey: .pageNumber)
        heading = try values.decodeIfPresent(String.self, forKey: .heading)
        marker = try values.decodeIfPresent(String.self, forKey: .marker)
        extractionType = try values.decodeIfPresent(String.self, forKey: .extractionType)
        chunkID = try values.decodeIfPresent(String.self, forKey: .chunkID)
        relatedCount = try values.decodeIfPresent(Int.self, forKey: .relatedCount)
        qualityWarnings = try values.decodeIfPresent([String].self, forKey: .qualityWarnings)
    }

    func locationDescription(language: AppLanguage) -> String? {
        if let pageNumber { return L10n.format("Страница %d", language: language, pageNumber) }
        if let heading, !heading.isEmpty { return L10n.format("Раздел: %@", language: language, heading) }
        return nil
    }
}

struct IndexStatus: Decodable {
    let sourceID: String
    let documents: Int
    let ready: Int
    let partial: Int
    let failed: Int
    let chunks: Int
    let lastIndexedAt: String?
    let issues: [IndexingIssue]?
    let embeddingTotal: Int?
    let embeddingReady: Int?

    enum CodingKeys: String, CodingKey {
        case documents, ready, partial, failed, chunks
        case sourceID = "source_id"
        case lastIndexedAt = "last_indexed_at"
        case issues
        case embeddingTotal = "embedding_total"
        case embeddingReady = "embedding_ready"
    }
}

enum IndexingState: Equatable {
    case notIndexed, queued, scanning, indexing, completed, completedWithWarnings
    case cancelling, cancelled, failed, unavailable

    func state(afterProgressPhase phase: String) -> IndexingState? {
        guard self != .cancelling, self != .cancelled else { return nil }
        return phase == "scanning" ? .scanning : .indexing
    }
}

struct IndexingProgress {
    let phase: String
    let current: Int
    let total: Int
    let indexed: Int
    let partial: Int
    let skipped: Int
    let failed: Int
}

struct IndexingIssue: Decodable, Identifiable {
    var id: String { "\(documentID):\(code):\(pageNumber ?? 0)" }
    let documentID: String
    let code: String
    let pageNumber: Int?

    enum CodingKeys: String, CodingKey {
        case code
        case documentID = "document_id"
        case pageNumber = "page_number"
    }

    init(documentID: String, code: String, pageNumber: Int? = nil) {
        self.documentID = documentID
        self.code = code
        self.pageNumber = pageNumber
    }
}

struct SearchWarning: Identifiable, Decodable {
    var id: String { "\(documentID):\(pageNumber.map(String.init) ?? "document"): \(code)" }
    let documentID: String
    let title: String
    let code: String
    let pageNumber: Int?

    enum CodingKeys: String, CodingKey {
        case title, code
        case documentID = "document_id"
        case pageNumber = "page_number"
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
    @Published private(set) var searchErrorDetails: String?
    @Published var searchWarnings: [SearchWarning] = []
    @Published var answerText: String?
    @Published private(set) var answerSources: [SearchHit] = []
    @Published var sourceSummaries: [SourceSummary] = []
    @Published var sourceLoadError: String?
    @Published private(set) var sourceIndexStatuses: [String: IndexStatus] = [:]
    @Published private(set) var indexingStates: [String: IndexingState] = [:]
    @Published private(set) var indexingProgress: [String: IndexingProgress] = [:]
    @Published private(set) var indexingIssues: [String: [IndexingIssue]] = [:]
    @Published var modelNames: [String] = []
    @Published var modelName: String {
        didSet { defaults.set(modelName, forKey: Keys.model) }
    }
    @Published var searchMode: SearchMode {
        didSet { defaults.set(searchMode.rawValue, forKey: Keys.searchMode); invalidateSearchProfile() }
    }
    @Published var embeddingModelName: String {
        didSet {
            defaults.set(embeddingModelName, forKey: Keys.embeddingModel)
            embeddingDimensions = embeddingModels.first(where: { $0.name == embeddingModelName })?.dimensions ?? 0
            invalidateSearchProfile()
        }
    }
    @Published private(set) var embeddingDimensions: Int {
        didSet { defaults.set(embeddingDimensions, forKey: Keys.embeddingDimensions) }
    }
    @Published var documentPrefix: String {
        didSet { defaults.set(documentPrefix, forKey: Keys.documentPrefix); invalidateSearchProfile() }
    }
    @Published var queryPrefix: String {
        didSet { defaults.set(queryPrefix, forKey: Keys.queryPrefix); invalidateSearchProfile() }
    }
    @Published var minimumSimilarity: Double {
        didSet {
            defaults.set(minimumSimilarity, forKey: Keys.minimumSimilarity)
            invalidateSearchResults()
            searchStatus = text("Настройки поиска изменены. Повторите поиск.")
        }
    }
    @Published private(set) var embeddingModels: [EmbeddingModel] = []
    @Published private(set) var embeddingModelStatus = ""
    @Published private(set) var semanticIndexNeedsPreparation = false
    private var profileRevision = UUID()
    private var modelRefreshID = UUID()

    var hasEmbeddingProfile: Bool { !embeddingModelName.isEmpty && embeddingDimensions > 0 }

    private var embeddingFields: [String: Any] {
        guard hasEmbeddingProfile else { return [:] }
        return ["embedding": ["model": embeddingModelName, "dimensions": embeddingDimensions,
                              "document_prefix": documentPrefix, "query_prefix": queryPrefix]]
    }

    private var retrievalFields: [String: Any] {
        var fields = embeddingFields
        fields["search_mode"] = searchMode.rawValue
        fields["min_similarity"] = minimumSimilarity
        return fields
    }

    private func invalidateSearchResults() {
        searchRequestID = UUID()
        isSearching = false
        hits = []
        searchErrorDetails = nil
        searchWarnings = []
        answerText = nil
        answerSources = []
    }

    private func invalidateSearchProfile() {
        profileRevision = UUID()
        invalidateSearchResults()
        sourceIndexStatuses = [:]
        semanticIndexNeedsPreparation = hasEmbeddingProfile
        searchStatus = text("Настройки поиска изменены. Подготовьте индекс и повторите поиск.")
        // Stop an old-profile batch; a new preparation will use the current profile.
        if let folderID = activeIndexFolderID { cancelIndexing(for: folderID, removing: false) }
    }

    func prepareSemanticIndex() {
        guard hasEmbeddingProfile else { return }
        semanticIndexNeedsPreparation = false
        // Active cancellation is asynchronous, so requeue it explicitly for the new profile.
        if let activeID = activeIndexFolderID,
           let folder = folders.first(where: { $0.id == activeID }),
           !pendingIndexFolders.contains(where: { $0.id == activeID }) {
            pendingIndexFolders.append(folder)
        }
        indexFolders(folders)
    }

    @Published var modelStatus = "Список моделей загружается с локального Ollama."
    @Published var ollamaStatus = "Проверка Ollama…"
    @Published var language: AppLanguage {
        didSet {
            defaults.set(language.rawValue, forKey: Keys.language)
            refreshSources()
            refreshModels()
            MenuBarLocalization.apply(language)
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
    @Published private(set) var hasFailedLibraryOperations = false
    @Published var firstRunPresentation: FirstRunPresentation?

    private let defaults = UserDefaults.standard
    private let bridge = MacBackendClient()
    private var didPromptSetupThisLaunch = false
    private var welcomeLeadsToSetup = false
    private var didScheduleInitialIndex = false
    private var pendingIndexFolders: [SavedFolder] = []
    private var pendingRemovalRoots: [String] = []
    private var failedIndexFolders: [SavedFolder] = []
    private var failedRemovalRoots: [String] = []
    private var activeIndexFolderID: UUID?
    private var activeIndexOperationID: UUID?
    private var cancelledIndexFolderIDs: Set<UUID> = []
    private var isIndexingFolders = false
    private var activeIndexTask: Task<[String: Any], Error>?
    private var searchRequestID = UUID()

    init() {
        Self.migrateLegacyPreferences(into: .standard)
        let initialLanguage = defaults.string(forKey: Keys.language)
            .flatMap(AppLanguage.init(rawValue:)) ?? .systemDefault
        language = initialLanguage
        searchStatus = L10n.text("Выберите папку в разделе «Библиотека», чтобы начать поиск.", language: initialLanguage)
        let savedTheme = defaults.string(forKey: Keys.theme).flatMap(AppTheme.init(rawValue:))
        theme = savedTheme ?? .system
        modelName = defaults.string(forKey: Keys.model) ?? "qwen3.5:4b"
        embeddingModelName = defaults.string(forKey: Keys.embeddingModel) ?? ""
        embeddingDimensions = defaults.integer(forKey: Keys.embeddingDimensions)
        documentPrefix = defaults.string(forKey: Keys.documentPrefix) ?? ""
        queryPrefix = defaults.string(forKey: Keys.queryPrefix) ?? ""
        minimumSimilarity = defaults.object(forKey: Keys.minimumSimilarity) == nil
            ? 0.35 : defaults.double(forKey: Keys.minimumSimilarity)
        searchMode = defaults.string(forKey: Keys.searchMode).flatMap(SearchMode.init(rawValue:)) ?? .lexical
        highContrast = defaults.bool(forKey: Keys.highContrast)
        reduceMotion = defaults.bool(forKey: Keys.reduceMotion)
        folders = Self.decodeFolders(from: defaults.data(forKey: Keys.folders))
        failedRemovalRoots = defaults.stringArray(forKey: Keys.pendingRemovals) ?? []
        updateFailedLibraryOperations()
        for index in folders.indices {
            folders[index].path = SavedFolder.path(of: folders[index])
        }
        saveFolders()
    }

    func text(_ source: String) -> String {
        L10n.text(source, language: language)
    }

    var setupCompleted: Bool {
        defaults.bool(forKey: "setup.completed.v1")
    }

    @discardableResult
    func presentInitialExperienceIfNeeded() -> Bool {
        guard !didPromptSetupThisLaunch else { return firstRunPresentation != nil }
        didPromptSetupThisLaunch = true
        if setupCompleted {
            defaults.set(true, forKey: Keys.introductionSeen)
            return false
        }
        if defaults.bool(forKey: Keys.introductionSeen) {
            firstRunPresentation = .setup
        } else {
            welcomeLeadsToSetup = true
            firstRunPresentation = .welcome
        }
        return true
    }

    func finishSetup() {
        defaults.set(true, forKey: "setup.completed.v1")
        firstRunPresentation = nil
        refreshSources()
        refreshModels()
    }

    func continueFromWelcome() {
        defaults.set(true, forKey: Keys.introductionSeen)
        firstRunPresentation = welcomeLeadsToSetup && !setupCompleted ? .setup : nil
        welcomeLeadsToSetup = false
    }

    func replayWelcome() {
        welcomeLeadsToSetup = false
        firstRunPresentation = .welcome
    }

    func dismissFirstRunPresentation() {
        firstRunPresentation = nil
        welcomeLeadsToSetup = false
    }

    func diagnoseBackend() async throws -> [String: Any] {
        try await bridge.request(command: "diagnose_backend")
    }

    func installOCRModel(progress: @escaping ([String: Any]) -> Void) async throws -> [String: Any] {
        try await bridge.requestStreaming(command: "install_ocr_model", progress: progress)
    }

    func addFolders(_ urls: [URL]) {
        var added = 0
        var addedFolders: [SavedFolder] = []
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
                let folder = SavedFolder(
                    id: UUID(), name: url.lastPathComponent, bookmark: bookmark,
                    path: SavedFolder.canonicalPath(url.path)
                )
                folders.append(folder)
                addedFolders.append(folder)
                indexingStates[folder.path ?? SavedFolder.canonicalPath(url.path)] = .notIndexed
                added += 1
            } catch {
                sourceLoadError = L10n.format(
                    "Не удалось сохранить доступ к папке «%@»: %@",
                    language: language,
                    url.lastPathComponent,
                    localizedError(error)
                )
            }
        }
        saveFolders()
        if added > 0 {
            invalidateSearchResults()
            selectedSection = .library
            if didScheduleInitialIndex { indexFolders(addedFolders) }
            refreshSources()
        }
    }

    func removeFolder(_ folder: SavedFolder) {
        invalidateSearchResults()
        let root = SavedFolder.path(of: folder)
        cancelIndexing(for: folder.id, removing: true)
        folders.removeAll { $0.id == folder.id }
        pendingIndexFolders.removeAll { $0.id == folder.id }
        failedIndexFolders.removeAll { $0.id == folder.id }
        updateFailedLibraryOperations()
        saveFolders()
        if let root { removeIndexedSource(root) }
        refreshSources()
    }

    func removeFolder(at path: String) {
        invalidateSearchResults()
        if let folder = folders.first(where: { SavedFolder.path(of: $0) == path }) {
            cancelIndexing(for: folder.id, removing: true)
        }
        folders.removeAll { SavedFolder.path(of: $0) == path }
        pendingIndexFolders.removeAll { SavedFolder.path(of: $0) == path }
        failedIndexFolders.removeAll { SavedFolder.path(of: $0) == path }
        updateFailedLibraryOperations()
        saveFolders()
        removeIndexedSource(path)
        refreshSources()
    }

    func refreshSources() {
        if !didScheduleInitialIndex {
            didScheduleInitialIndex = true
            indexFolders(folders)
            retryFailedLibraryOperations()
        }
        Task {
            do {
                let response = try await bridge.request(command: "list_sources", fields: [
                    "roots": SavedFolder.searchRoots(folders)
                ])
                sourceSummaries = try response.decode("sources", as: [SourceSummary].self)
                sourceLoadError = nil
                refreshIndexStatuses(for: sourceSummaries)
            } catch {
                sourceLoadError = localizedError(error)
            }
        }
    }

    private func indexFolders(_ selected: [SavedFolder]) {
        for folder in selected where folders.contains(where: { $0.id == folder.id }) {
            if activeIndexFolderID != folder.id && !pendingIndexFolders.contains(where: { $0.id == folder.id }) {
                pendingIndexFolders.append(folder)
                if let path = SavedFolder.path(of: folder) { indexingStates[path] = .queued }
            }
        }
        drainIndexQueue()
    }

    func syncFolder(_ folder: SavedFolder) {
        indexFolders([folder])
    }

    func syncFolder(at path: String) {
        guard let folder = folders.first(where: { SavedFolder.path(of: $0) == path }) else {
            sourceLoadError = text("Источник больше не подключён.")
            return
        }
        indexFolders([folder])
    }

    func cancelIndexing(for folder: SavedFolder) {
        cancelIndexing(for: folder.id, removing: false)
    }

    func canCancelIndexing(at path: String) -> Bool {
        guard let folder = folders.first(where: { SavedFolder.path(of: $0) == path }) else { return false }
        return activeIndexFolderID == folder.id || pendingIndexFolders.contains(where: { $0.id == folder.id })
    }

    private func cancelIndexing(for folderID: UUID, removing: Bool) {
        guard let folder = folders.first(where: { $0.id == folderID }),
              let root = SavedFolder.path(of: folder) else { return }
        if pendingIndexFolders.contains(where: { $0.id == folderID }) {
            pendingIndexFolders.removeAll { $0.id == folderID }
            if !removing { indexingStates[root] = .cancelled }
        }
        if activeIndexFolderID == folderID {
            indexingStates[root] = .cancelling
            cancelledIndexFolderIDs.insert(folderID)
            activeIndexTask?.cancel()
        }
    }

    func stateLabel(for source: SourceSummary) -> String {
        let root = SavedFolder.canonicalPath(source.path)
        let state = indexingStates[root] ?? stateFromBackend(source)
        switch state {
        case .notIndexed: return text("Не индексировано")
        case .queued: return text("В очереди")
        case .scanning: return text("Поиск документов…")
        case .indexing: return text("Индексация…")
        case .completed: return text("Индекс актуален")
        case .completedWithWarnings: return text("Готово с предупреждениями")
        case .cancelling: return text("Останавливаем обработку…")
        case .cancelled: return text("Обработка остановлена")
        case .failed: return text("Ошибка индексации")
        case .unavailable: return text("Источник недоступен")
        }
    }

    func sourceSummary(for source: SourceSummary) -> String {
        let status = sourceIndexStatuses[SavedFolder.canonicalPath(source.path)]
        guard let status else {
            return L10n.format("%d документов", language: language, source.documentCount)
        }
        let summary = L10n.format("%d документов · %d фрагментов", language: language, status.documents, status.chunks)
        if let total = status.embeddingTotal, let ready = status.embeddingReady, hasEmbeddingProfile {
            return summary + " · " + L10n.format("Векторы: %d из %d", language: language, ready, total)
        }
        return summary
    }

    func progressLabel(for source: SourceSummary) -> String? {
        guard let progress = indexingProgress[SavedFolder.canonicalPath(source.path)] else { return nil }
        if progress.phase == "embedding" {
            return L10n.format("Расчёт эмбеддингов: %d из %d", language: language, progress.current, progress.total)
        }
        let count = L10n.format("Обработано: %d · Пропущено: %d · Ошибок: %d", language: language, progress.indexed + progress.partial, progress.skipped, progress.failed)
        if progress.total > 0 {
            return L10n.format("Обрабатываются документы: %d из %d\n%@", language: language, progress.current, progress.total, count)
        }
        return text("Поиск документов…") + "\n" + count
    }

    func issueMessage(_ code: String) -> String {
        switch code {
        case "embedding_error": return text("Не удалось рассчитать эмбеддинги. Проверьте локальную модель и повторите подготовку индекса.")
        case "embedding_required": return text("Выберите установленную embedding-модель в настройках поиска.")
        case "model_unavailable": return text("Локальная модель недоступна. Обновите список моделей в настройках.")
        case "invalid_citations": return text("Модель вернула непроверяемые ссылки. Найденные фрагменты доступны ниже.")
        case "no_context": return text("В материалах недостаточно данных для ответа.")
        case "document_extraction_failed": return text("Не удалось прочитать документ. Проверьте файл и повторите обработку.")
        case "ocr_failed": return text("Не удалось выполнить OCR. Проверьте Chandra OCR в настройках.")
        case "document_disappeared": return text("Файл исчез во время обработки. Проверьте папку и повторите синхронизацию.")
        case "permission_denied": return text("Нет доступа к файлу. Проверьте права доступа к папке.")
        case "document_stat_failed": return text("Не удалось проверить файл. Проверьте доступность файла.")
        case "backend_missing": return text("Не найден встроенный локальный backend. Переустановите приложение.")
        case "backend_invalid_response": return text("Локальный backend вернул некорректный ответ. Повторите операцию.")
        case "backend_error": return text("Локальный backend не смог выполнить операцию. Повторите попытку.")
        case "index_busy": return text("Индексация занята. Дождитесь завершения другой операции.")
        case "source_unavailable": return text("Папка недоступна. Подключите её снова и повторите синхронизацию.")
        case "indexing_failed": return text("Не удалось завершить индексацию. Проверьте папку и повторите попытку.")
        default: return text("Не удалось обработать документ. Проверьте файл и повторите синхронизацию.")
        }
    }

    private func stateFromBackend(_ source: SourceSummary) -> IndexingState {
        let root = SavedFolder.canonicalPath(source.path)
        guard source.available != false else { return .unavailable }
        guard let status = sourceIndexStatuses[root] else { return .notIndexed }
        if status.failed > 0 || status.partial > 0 { return .completedWithWarnings }
        return status.lastIndexedAt == nil ? .notIndexed : .completed
    }

    private func refreshIndexStatuses(for sources: [SourceSummary]) {
        let revision = profileRevision
        let profile = embeddingFields
        Task {
            for source in sources {
                let root = SavedFolder.canonicalPath(source.path)
                do {
                    var fields = profile
                    fields["root"] = source.path
                    let response = try await bridge.request(command: "index_status", fields: fields)
                    guard revision == profileRevision else { return }
                    let data = try JSONSerialization.data(withJSONObject: response, options: [.fragmentsAllowed])
                    let status = try JSONDecoder().decode(IndexStatus.self, from: data)
                    sourceIndexStatuses[root] = status
                    if !isIndexingStateActive(indexingStates[root]), let issues = status.issues {
                        indexingIssues[root] = issues
                    }
                    if indexingStates[root] == nil || [.completed, .completedWithWarnings, .notIndexed, .unavailable].contains(where: { sameState($0, indexingStates[root]) }) {
                        indexingStates[root] = stateFromBackend(source)
                    }
                } catch {
                    if source.available == false { indexingStates[root] = .unavailable }
                }
            }
        }
    }

    private func sameState(_ lhs: IndexingState, _ rhs: IndexingState?) -> Bool {
        guard let rhs else { return false }
        switch (lhs, rhs) {
        case (.completed, .completed), (.completedWithWarnings, .completedWithWarnings), (.notIndexed, .notIndexed), (.unavailable, .unavailable): return true
        default: return false
        }
    }

    private func isIndexingStateActive(_ state: IndexingState?) -> Bool {
        guard let state else { return false }
        return [.queued, .scanning, .indexing, .cancelling].contains(state)
    }

    private func removeIndexedSource(_ root: String) {
        failedRemovalRoots.removeAll { $0 == root }
        if !pendingRemovalRoots.contains(root) { pendingRemovalRoots.append(root) }
        savePendingRemovals()
        updateFailedLibraryOperations()
        drainIndexQueue()
    }

    func retryFailedLibraryOperations() {
        guard hasFailedLibraryOperations else { return }
        for root in failedRemovalRoots where !pendingRemovalRoots.contains(root) {
            pendingRemovalRoots.append(root)
        }
        for folder in failedIndexFolders where folders.contains(where: { $0.id == folder.id }) {
            if activeIndexFolderID != folder.id && !pendingIndexFolders.contains(where: { $0.id == folder.id }) {
                pendingIndexFolders.append(folder)
            }
        }
        failedRemovalRoots.removeAll()
        failedIndexFolders.removeAll()
        updateFailedLibraryOperations()
        drainIndexQueue()
    }

    private func savePendingRemovals() {
        defaults.set(pendingRemovalRoots + failedRemovalRoots, forKey: Keys.pendingRemovals)
    }

    private func updateFailedLibraryOperations() {
        hasFailedLibraryOperations = !failedIndexFolders.isEmpty || !failedRemovalRoots.isEmpty
    }

    private func drainIndexQueue() {
        guard !isIndexingFolders else { return }
        isIndexingFolders = true
        Task {
            while !pendingRemovalRoots.isEmpty || !pendingIndexFolders.isEmpty {
                if !pendingRemovalRoots.isEmpty {
                    let root = pendingRemovalRoots.removeFirst()
                    if folders.contains(where: { SavedFolder.path(of: $0) == root }) {
                        savePendingRemovals()
                        continue
                    }
                    do {
                        _ = try await bridge.request(command: "remove_index_source", fields: ["root": root])
                        savePendingRemovals()
                    } catch BackendClientError.indexBusy {
                        if !pendingRemovalRoots.contains(root) { pendingRemovalRoots.append(root) }
                        try? await Task.sleep(for: .seconds(2))
                    } catch {
                        if !failedRemovalRoots.contains(root) { failedRemovalRoots.append(root) }
                        savePendingRemovals()
                        updateFailedLibraryOperations()
                        sourceLoadError = localizedError(error)
                    }
                    continue
                }
                let folder = pendingIndexFolders.removeFirst()
                guard folders.contains(where: { $0.id == folder.id }) else { continue }
                activeIndexFolderID = folder.id
                let operationID = UUID()
                activeIndexOperationID = operationID
                let rootPath = SavedFolder.path(of: folder) ?? folder.path ?? ""
                indexingStates[rootPath] = .scanning
                do {
                    let (urls, opened) = try openFolderURLs(for: [folder])
                    defer { closeFolderURLs(urls, opened: opened) }
                    guard let root = urls.first else { activeIndexFolderID = nil; activeIndexOperationID = nil; continue }
                    if cancelledIndexFolderIDs.remove(folder.id) != nil {
                        indexingStates[rootPath] = removingFolder(folder.id) ? .notIndexed : .cancelled
                        activeIndexFolderID = nil
                        activeIndexOperationID = nil
                        continue
                    }
                    let fields = embeddingFields.merging(["root": root.path]) { _, new in new }
                    let task = Task {
                        try await bridge.requestStreaming(
                        command: "sync_source",
                        fields: fields,
                        progress: { update in
                            guard self.activeIndexFolderID == folder.id,
                                  self.activeIndexOperationID == operationID,
                                  let phase = update["phase"] as? String else { return }
                            guard let state = self.indexingStates[rootPath]?.state(afterProgressPhase: phase) else { return }
                            let current = update["current"] as? Int ?? 0
                            let total = update["total"] as? Int ?? 0
                            self.indexingStates[rootPath] = state
                            self.indexingProgress[rootPath] = IndexingProgress(
                                phase: phase,
                                current: current,
                                total: total,
                                indexed: update["indexed"] as? Int ?? 0,
                                partial: update["partial"] as? Int ?? 0,
                                skipped: update["skipped"] as? Int ?? 0,
                                failed: update["failed"] as? Int ?? 0
                            )
                        }
                        )
                    }
                    activeIndexTask = task
                    let report = try await task.value
                    activeIndexTask = nil
                    let cancelled = (try? report.decode("cancelled", as: Bool.self)) ?? false
                    let failed = (try? report.decode("failed", as: Int.self)) ?? 0
                    let partial = (try? report.decode("partial", as: Int.self)) ?? 0
                    indexingIssues[rootPath] = (try? report.decode("errors", as: [IndexingIssue].self)) ?? []
                    indexingStates[rootPath] = cancelled ? .cancelled : (failed > 0 || partial > 0 ? .completedWithWarnings : .completed)
                    indexingProgress[rootPath] = nil
                    refreshSources()
                    if !folders.contains(where: { $0.id == folder.id }) {
                        removeIndexedSource(root.path)
                    }
                } catch BackendClientError.indexBusy {
                    activeIndexTask = nil
                    activeIndexOperationID = nil
                    cancelledIndexFolderIDs.remove(folder.id)
                    if folders.contains(where: { $0.id == folder.id }) {
                        pendingIndexFolders.append(folder)
                        indexingStates[rootPath] = .queued
                    }
                    try? await Task.sleep(for: .seconds(2))
                } catch is CancellationError {
                    activeIndexTask = nil
                    activeIndexOperationID = nil
                    cancelledIndexFolderIDs.remove(folder.id)
                    indexingProgress[rootPath] = nil
                    if !pendingRemovalRoots.contains(rootPath) && !removingFolder(folder.id) {
                        indexingStates[rootPath] = .cancelled
                    }
                } catch {
                    activeIndexTask = nil
                    activeIndexOperationID = nil
                    cancelledIndexFolderIDs.remove(folder.id)
                    indexingProgress[rootPath] = nil
                    indexingStates[rootPath] = (sourceSummaries.first(where: { SavedFolder.canonicalPath($0.path) == rootPath })?.available == false) ? .unavailable : .failed
                    if folders.contains(where: { $0.id == folder.id }) &&
                        !failedIndexFolders.contains(where: { $0.id == folder.id }) {
                        failedIndexFolders.append(folder)
                    }
                    updateFailedLibraryOperations()
                    indexingIssues[rootPath] = [IndexingIssue(documentID: folder.name, code: issueCode(for: error))]
                }
                activeIndexFolderID = nil
                activeIndexOperationID = nil
            }
            isIndexingFolders = false
            refreshSources()
        }
    }

    private func removingFolder(_ id: UUID) -> Bool {
        !folders.contains(where: { $0.id == id })
    }

    private func issueCode(for error: Error) -> String {
        if let backendError = error as? BackendClientError { return backendError.code }
        if let cocoaError = error as? CocoaError, cocoaError.code == .fileReadNoPermission {
            return "permission_denied"
        }
        if let cocoaError = error as? CocoaError, cocoaError.code == .fileNoSuchFile {
            return "source_unavailable"
        }
        return "indexing_failed"
    }

    func refreshModels() {
        refreshEmbeddingModels()
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

    func refreshEmbeddingModels() {
        modelRefreshID = UUID()
        let refreshID = modelRefreshID
        Task {
            do {
                let response = try await bridge.request(command: "list_embedding_models")
                guard refreshID == modelRefreshID else { return }
                embeddingModels = try response.decode("models", as: [EmbeddingModel].self)
                if let selected = embeddingModels.first(where: { $0.name == embeddingModelName }),
                   selected.dimensions != embeddingDimensions {
                    embeddingDimensions = selected.dimensions
                    invalidateSearchProfile()
                }
                embeddingModelStatus = embeddingModels.isEmpty
                    ? text("Нет установленных embedding-моделей. Установите модель в Ollama и обновите список.")
                    : text("Используются только установленные локальные модели. Загрузка не запускается.")
            } catch {
                guard refreshID == modelRefreshID else { return }
                embeddingModels = []
                embeddingModelStatus = localizedError(error)
            }
        }
    }

    func saveModel() {
        let trimmed = modelName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            modelName = ""
            return
        }
        modelName = trimmed
        modelStatus = L10n.format("Модель «%@» сохранена на этом компьютере.", language: language, trimmed)
    }

    func search() {
        let searchText = query.trimmingCharacters(in: .whitespacesAndNewlines)
        searchRequestID = UUID()
        let requestID = searchRequestID
        isSearching = false
        guard !searchText.isEmpty else {
            searchStatus = text("Введите тему или вопрос для поиска.")
            hits = []
            searchWarnings = []
            answerText = nil
            answerSources = []
            return
        }
        guard !folders.isEmpty else {
            searchStatus = text("Сначала подключите папку в разделе «Библиотека».")
            return
        }

        guard searchMode == .lexical || hasEmbeddingProfile else {
            searchStatus = issueMessage("embedding_required")
            isSearching = false
            return
        }
        isSearching = true
        hits = []
        searchErrorDetails = nil
        searchWarnings = []
        answerText = nil
        answerSources = []
        searchStatus = text("Ищу в подключённых материалах…")
        Task {
            do {
                var fields = retrievalFields
                fields["roots"] = SavedFolder.searchRoots(folders)
                fields["query"] = searchText
                let searchResponse = try await bridge.request(command: "search", fields: fields)
                guard requestID == searchRequestID else { return }
                let found = try searchResponse.decode("hits", as: [SearchHit].self)
                searchWarnings = (try? searchResponse.decode("warnings", as: [SearchWarning].self)) ?? []
                hits = found
                let pending = (try? searchResponse.decode("embedding_pending", as: Bool.self)) ?? false
                if pending { semanticIndexNeedsPreparation = true }
                guard !found.isEmpty else {
                    let backendIndexing = (try? searchResponse.decode("indexing", as: Bool.self)) ?? false
                    searchStatus = pending ? text("Семантический индекс ещё не готов. Подготовьте его в настройках поиска.") : backendIndexing || isIndexingFolders
                        ? text("Материалы ещё индексируются. Повторите поиск после завершения обработки.")
                        : text("В выбранных материалах не нашёл фрагментов по этому запросу.")
                    isSearching = false
                    return
                }
                guard !modelName.isEmpty, modelNames.contains(modelName) else {
                    searchStatus = pending
                        ? text("Фрагменты найдены. Семантический индекс ещё не готов; подготовьте его в настройках.")
                        : L10n.format("Найдено %d фрагментов. Для ответа выберите локальную языковую модель.", language: language, found.count)
                    isSearching = false
                    return
                }
                searchStatus = L10n.format("Нашёл %d фрагментов. Формирую ответ локально…", language: language, found.count)
                fields["model"] = modelName
                fields["language"] = language.rawValue
                let answerResponse = try await bridge.request(command: "answer", fields: fields)
                guard requestID == searchRequestID else { return }
                let generatedAnswer = try answerResponse.decode("answer", as: String.self)
                let sources = try answerResponse.decode("sources", as: [SearchHit].self)
                let grounded = try answerResponse.decode("grounded", as: Bool.self)
                answerText = generatedAnswer.isEmpty ? nil : generatedAnswer
                answerSources = generatedAnswer.isEmpty || !grounded ? [] : sources
                searchStatus = grounded ? L10n.format(
                    "Ответ подготовлен локально по %d источникам.",
                    language: language,
                    answerSources.count
                ) : text("В материалах недостаточно данных для ответа.")
            } catch {
                if requestID == searchRequestID {
                    searchStatus = localizedError(error)
                    searchErrorDetails = (error as? BackendClientError)?.technicalDetails
                }
            }
            if requestID == searchRequestID { isSearching = false }
        }
    }

    func open(_ hit: SearchHit) {
        guard let folder = folders.first(where: { SavedFolder.path(of: $0) == hit.sourceRoot }) else {
            searchStatus = text("Источник больше не подключён.")
            return
        }
        do {
            let (urls, opened) = try openFolderURLs(for: [folder])
            defer { closeFolderURLs(urls, opened: opened) }
            guard let root = urls.first else { return }
            let fileURL = root.appending(path: hit.documentID).standardizedFileURL
            let canonicalRoot = SavedFolder.canonicalPath(root.path)
            let canonicalFile = SavedFolder.canonicalPath(fileURL.path)
            guard fileURL.path.hasPrefix(root.standardizedFileURL.path + "/"),
                  FileManager.default.fileExists(atPath: fileURL.path),
                  canonicalFile.hasPrefix(canonicalRoot + "/") else {
                searchStatus = text("Исходный файл недоступен. Найденный фрагмент сохранён в индексе; подключите папку снова.")
                return
            }
            NSWorkspace.shared.open(fileURL)
        } catch {
            searchStatus = localizedError(error)
        }
    }

    private func localizedError(_ error: Error) -> String {
        if let backend = error as? BackendClientError {
            if backend.code == "invalid_citations" {
                return text("Поиск выполнен, ответ модели не показан.") + "\n"
                    + text(backend.citationReasonMessage) + "\n"
                    + text("Найденные фрагменты доступны ниже. Сверьте их с оригиналом или повторите ответ с другой локальной моделью.")
            }
            return issueMessage(backend.code)
        }
        return L10n.text(error.localizedDescription, language: language)
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
            let canonicalPath = SavedFolder.canonicalPath(url.path)
            if folder.path != canonicalPath {
                updatePath(canonicalPath, for: folder.id)
            }
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

    private func updatePath(_ path: String, for id: UUID) {
        guard let index = folders.firstIndex(where: { $0.id == id }) else { return }
        folders[index].path = path
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
                return SavedFolder(
                    id: UUID(), name: url.lastPathComponent, bookmark: bookmark,
                    path: url.standardizedFileURL.path
                )
            }
            if let data = try? JSONEncoder().encode(folders) {
                defaults.set(data, forKey: Keys.folders)
            }
        }
        defaults.set(true, forKey: Keys.migrated)
    }
}

private enum Keys {
    static let searchMode = "search.mode.v1"
    static let embeddingModel = "search.embedding.model.v1"
    static let embeddingDimensions = "search.embedding.dimensions.v1"
    static let documentPrefix = "search.embedding.document_prefix.v1"
    static let queryPrefix = "search.embedding.query_prefix.v1"
    static let minimumSimilarity = "search.minimum_similarity.v1"
    static let folders = "library.bookmarks.v1"
    static let pendingRemovals = "library.pending_removals.v1"
    static let model = "model"
    static let language = "general/language"
    static let theme = "appearance/theme"
    static let highContrast = "appearance/high_contrast"
    static let reduceMotion = "appearance/reduce_motion"
    static let migrated = "migration.fromQt.v1"
    static let introductionSeen = "onboarding.introduction.seen.v1"
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
                        if error?["code"] as? String == "index_busy" {
                            throw BackendClientError.indexBusy
                        }
                        throw BackendClientError.fromEnvelope(error)
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
        let requestID = UUID().uuidString
        request["request_id"] = requestID
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
                                   message["request_id"] as? String == requestID,
                                   let value = message["result"] as? [String: Any] {
                                    DispatchQueue.main.async { progress(value) }
                                } else if message["request_id"] as? String == requestID {
                                    finalEnvelope = message
                                }
                            }
                        }
                        process.waitUntilExit()
                        if control.isCancelled { throw CancellationError() }
                        guard process.terminationStatus == 0,
                              let envelope = finalEnvelope,
                              envelope["request_id"] as? String == requestID else {
                            throw BackendClientError.invalidResponse
                        }
                        guard envelope["ok"] as? Bool == true,
                              let result = envelope["result"] as? [String: Any] else {
                            let error = envelope["error"] as? [String: Any]
                            if error?["code"] as? String == "index_busy" {
                                throw BackendClientError.indexBusy
                            }
                            throw BackendClientError.fromEnvelope(error)
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
        #if DEBUG
        if let path = ProcessInfo.processInfo.environment["STUDY_AGENT_BACKEND_EXECUTABLE"] {
            return URL(fileURLWithPath: path)
        }
        #endif
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

enum BackendClientError: LocalizedError {
    case missingBackend
    case invalidResponse
    case indexBusy
    case backend(code: String, reason: String? = nil, sourceCount: Int? = nil,
                 invalidSources: [Int]? = nil, paragraphIndex: Int? = nil,
                 warningCodes: [String]? = nil, stage: String? = nil, model: String? = nil)

    static func fromEnvelope(_ payload: [String: Any]?) -> BackendClientError {
        let details = payload?["details"] as? [String: Any]
        return .backend(code: payload?["code"] as? String ?? "backend_error",
            reason: payload?["reason"] as? String, sourceCount: details?["source_count"] as? Int,
            invalidSources: details?["invalid_sources"] as? [Int],
            paragraphIndex: details?["paragraph_index"] as? Int,
            warningCodes: details?["warning_codes"] as? [String],
            stage: payload?["stage"] as? String, model: payload?["model"] as? String)
    }

    var citationReasonMessage: String {
        guard case .backend(_, let reason, _, _, _, _, _, _) = self else { return "" }
        switch reason {
        case "missing_citations": return "Модель не указала ссылки на найденные источники."
        case "unknown_source": return "Модель сослалась на источник, которого нет в переданном контексте."
        case "uncited_paragraph": return "В ответе есть содержательный абзац без ссылки на источник."
        case "generated_links": return "Модель добавила внешнюю или Markdown-ссылку вместо проверяемого номера источника."
        case "source_quality": return "В найденном материале обнаружены признаки ошибки распознавания формулы; достоверность ответа не подтверждена."
        default: return "Ответ не прошёл проверку ссылок на источники."
        }
    }

    var technicalDetails: String {
        guard case .backend(let code, let reason, let count, let invalid, let paragraph, let warnings, let stage, let model) = self else { return code }
        var fields = ["code: \(code)"]
        if let reason { fields.append("reason: \(reason)") }
        if let stage { fields.append("stage: \(stage)") }
        if let model { fields.append("model: \(model)") }
        if let count { fields.append("source_count: \(count)") }
        if let invalid { fields.append("invalid_sources: \(invalid)") }
        if let paragraph { fields.append("paragraph_index: \(paragraph)") }
        if let warnings { fields.append("warning_codes: \(warnings.joined(separator: ", "))") }
        return fields.joined(separator: "\n")
    }

    var code: String {
        switch self {
        case .missingBackend: "backend_missing"
        case .invalidResponse: "backend_invalid_response"
        case .indexBusy: "index_busy"
        case .backend(let code, _, _, _, _, _, _, _): code
        }
    }

    var errorDescription: String? {
        switch self {
        case .missingBackend: "Не найден встроенный локальный backend. Соберите приложение скриптом scripts/build_macos_native_app.sh."
        case .invalidResponse: "Локальный backend вернул некорректный ответ."
        case .indexBusy: "Индексация занята другим процессом. Повторяем запрос."
        case .backend: "Локальный backend не смог выполнить операцию. Повторите попытку."
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
