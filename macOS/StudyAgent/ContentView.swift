import AppKit
import Combine
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject private var model: StudyAgentModel
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    private static let sidebarLogo: NSImage? = {
        guard let url = Bundle.main.url(forResource: "AppIcon_1024", withExtension: "png") else {
            return nil
        }
        return NSImage(contentsOf: url)
    }()

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            List(selection: $model.selectedSection) {
                ForEach(MainSection.allCases) { section in
                    Label(model.text(section.title(language: model.language)), systemImage: section.symbol)
                        .tag(section)
                }
            }
            .listStyle(.sidebar)
            .safeAreaInset(edge: .top, spacing: 0) {
                if let logo = Self.sidebarLogo {
                    HStack(spacing: 10) {
                        Image(nsImage: logo)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 30, height: 30)
                            .accessibilityHidden(true)
                        Text("Study Agent")
                            .font(.headline)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                Label(model.ollamaStatus, systemImage: "circle.fill")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .accessibilityLabel(model.ollamaStatus)
            }
            .navigationSplitViewColumnWidth(min: 180, ideal: 220, max: 260)

        } detail: {
            Group {
                switch model.selectedSection {
                case .search:
                    SearchPanel()
                case .library:
                    LibraryPanel()
                }
            }
            .frame(minWidth: 520, maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .navigationSplitViewStyle(.balanced)
        .frame(minWidth: 760, minHeight: 560)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                if model.selectedSection == .library {
                    Button(model.text("Добавить папку"), systemImage: "folder.badge.plus") {
                        model.isImportingFolders = true
                    }
                    .help(model.text("Добавить папку с учебными материалами"))
                }
            }
            ToolbarItem(placement: .automatic) {
                SettingsLink {
                    Label(model.text("Настройки"), systemImage: "gearshape")
                }
                .help(model.text("Настройки Study Agent"))
            }
        }
        .fileImporter(
            isPresented: $model.isImportingFolders,
            allowedContentTypes: [.folder],
            allowsMultipleSelection: true
        ) { result in
            switch result {
            case .success(let urls):
                model.addFolders(urls)
            case .failure(let error):
                model.sourceLoadError = model.text(error.localizedDescription)
            }
        }
        .task {
            let presentingFirstRun = model.presentInitialExperienceIfNeeded()
            guard !presentingFirstRun else { return }
            model.refreshSources()
            model.refreshModels()
        }
        .sheet(
            isPresented: Binding(
                get: { model.firstRunPresentation != nil },
                set: { if !$0 { model.dismissFirstRunPresentation() } }
            ),
            onDismiss: {
                if !model.setupCompleted {
                    model.refreshSources()
                    model.refreshModels()
                }
            }
        ) {
            FirstRunFlowView()
                .environmentObject(model)
        }
        .onAppear {
            MenuBarLocalization.apply(model.language)
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            model.retryFailedLibraryOperations()
        }
        .onChange(of: model.language) { _, language in MenuBarLocalization.apply(language) }
        .onChange(of: model.firstRunPresentation) { _, _ in MenuBarLocalization.apply(model.language) }
        .contrast(model.highContrast || colorSchemeContrast == .increased ? 1.18 : 1.0)
        .animation(model.reduceMotion || systemReduceMotion ? nil : .easeOut(duration: 0.15), value: model.selectedSection)
    }
}

private struct FirstRunFlowView: View {
    @EnvironmentObject private var model: StudyAgentModel

    var body: some View {
        Group {
            if model.firstRunPresentation == .welcome {
                WelcomeView(onContinue: model.continueFromWelcome)
                    .frame(minWidth: 680, minHeight: 500)
            } else {
                SetupWizard()
                    .frame(minWidth: 680, minHeight: 530)
            }
        }
    }
}

private struct SearchPanel: View {
    @EnvironmentObject private var model: StudyAgentModel

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            PageHeading(
                title: model.text("Поиск по материалам"),
                subtitle: model.text("Ответы строятся локальной моделью по выбранным источникам.")
            )

            HStack(spacing: 12) {
                TextField(model.text("Спросите о лекциях, конспектах или учебниках…"), text: $model.query)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(model.search)
                    .accessibilityLabel(model.text("Вопрос по учебным материалам"))
                Button {
                    model.search()
                } label: {
                    if model.isSearching {
                        ProgressView().controlSize(.small)
                    } else {
                        Label(model.text("Спросить"), systemImage: "arrow.up.circle.fill")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(model.isSearching)
                .keyboardShortcut(.return, modifiers: .command)
            }

            Label(model.searchStatus, systemImage: model.hits.isEmpty ? "info.circle" : "doc.text.magnifyingglass")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if !model.searchWarnings.isEmpty {
                        GroupBox {
                            VStack(alignment: .leading, spacing: 6) {
                                ForEach(model.searchWarnings) { warning in
                                    Text(warning.documentID + (warning.pageNumber.map { " · \(model.text("Страница")) \($0)" } ?? ""))
                                        .lineLimit(nil)
                                        .textSelection(.enabled)
                                    Text(model.text(warning.code == "ocr_failed" ? "Не удалось распознать страницу" : "Не удалось прочитать документ"))
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        } label: {
                            Label(model.text("Предупреждения обработки") + ": \(model.searchWarnings.count)", systemImage: "exclamationmark.triangle")
                        }
                        .accessibilityElement(children: .combine)
                    }
                    if let details = model.searchErrorDetails {
                        DisclosureGroup(model.text("Технические подробности")) {
                            Text(verbatim: details).font(.caption.monospaced()).textSelection(.enabled)
                        }
                    }
                    if model.hits.contains(where: { MathContentView.containsMath($0.excerpt) }) {
                        Text(model.text("Фрагменты из источников; математическая корректность автоматически не проверена."))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if let answer = model.answerText {
                        GroupBox(model.text("Ответ")) {
                            VStack(alignment: .leading, spacing: 12) {
                                MathContentView(text: answer, language: model.language)
                                if !model.answerSources.isEmpty {
                                    Divider()
                                    Text(model.text("Использованные источники"))
                                        .font(.headline)
                                    ForEach(Array(model.answerSources.enumerated()), id: \.element.id) { index, hit in
                                        SearchSourceCard(hit: hit, number: index + 1, initiallyExpanded: false)
                                    }
                                }
                            }
                            .padding(.top, 4)
                        }
                    }
                    ForEach(model.hits) { hit in
                        SearchSourceCard(hit: hit, number: nil, initiallyExpanded: true)
                    }
                }
            }
        }
        .padding(28)
    }
}

/// Compact provenance header; the disclosure displays the complete saved chunk.
private struct SearchSourceCard: View {
    @EnvironmentObject private var model: StudyAgentModel
    let hit: SearchHit
    let number: Int?
    @State private var expanded: Bool

    init(hit: SearchHit, number: Int?, initiallyExpanded: Bool) {
        self.hit = hit
        self.number = number
        _expanded = State(initialValue: initiallyExpanded)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text((number.map { "[\($0)] " } ?? "") + URL(filePath: hit.documentID).lastPathComponent)
                        .font(.subheadline.weight(.semibold))
                        .textSelection(.enabled)
                    Text("\(URL(filePath: hit.sourceRoot).lastPathComponent)/\(hit.documentID)")
                        .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                }
                Spacer(minLength: 8)
                Button { model.open(hit) } label: {
                    Image(systemName: "arrow.up.forward.square")
                }
                .buttonStyle(.borderless)
                .help(model.text("Открыть исходный документ"))
                .accessibilityLabel(model.text("Открыть исходный документ"))
            }
            DisclosureGroup("Original Text", isExpanded: $expanded) {
                VStack(alignment: .leading, spacing: 8) {
                    if let location = hit.locationDescription(language: model.language) {
                        Text(location).font(.caption).foregroundStyle(.secondary)
                    }
                    MathContentView(text: hit.displayExcerpt, language: model.language)
                    if hit.qualityWarnings?.contains("formula_suspect") == true {
                        Label(model.text("В формуле возможна ошибка распознавания. Сверьте с оригиналом."), systemImage: "exclamationmark.triangle")
                            .font(.caption).foregroundStyle(.orange)
                    }
                }
                .padding(.top, 6)
            }
            .font(.caption)
            if let related = hit.relatedCount, related > 0 {
                Text(L10n.format("Ещё %d совпадений в этом разделе", language: model.language, related))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(.quaternary))
    }
}

private struct LibraryPanel: View {
    @EnvironmentObject private var model: StudyAgentModel

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            PageHeading(
                title: model.text("Библиотека"),
                subtitle: model.text("Подключайте только те папки, которые хотите искать. Файлы не покидают этот компьютер.")
            )

            if model.hasFailedLibraryOperations {
                HStack {
                    Text(model.text("Не все операции с библиотекой завершены."))
                    Spacer()
                    Button(model.text("Повторить"), systemImage: "arrow.clockwise") {
                        model.retryFailedLibraryOperations()
                    }
                }
            }

            if let error = model.sourceLoadError {
                Label(error, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if model.sourceSummaries.isEmpty {
                ContentUnavailableView {
                    Label(model.text("Папки пока не добавлены"), systemImage: "folder.badge.plus")
                } description: {
                    Text(model.text("Добавьте папку с PDF, изображениями, Markdown или TXT."))
                } actions: {
                    Button(model.text("Добавить папку…"), systemImage: "folder.badge.plus") {
                        model.isImportingFolders = true
                    }
                    .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(model.sourceSummaries) { source in
                        SourceRow(source: source) {
                            model.removeFolder(at: source.path)
                        }
                    }
                }
                .listStyle(.inset)
            }
        }
        .padding(28)
        .foregroundStyle(Color(nsColor: .labelColor))
    }
}

private struct SourceRow: View {
    @EnvironmentObject private var model: StudyAgentModel
    let source: SourceSummary
    let remove: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: "folder.fill")
                .font(.title2)
                .foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 4) {
                Text(source.name).font(.headline)
                Text(model.sourceSummary(for: source))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Label(model.stateLabel(for: source), systemImage: stateSymbol)
                    .font(.caption)
                    .foregroundStyle(stateColor)
                if let progress = model.progressLabel(for: source) {
                    if let status = model.indexingProgress[SavedFolder.canonicalPath(source.path)], status.total > 0 {
                        ProgressView(value: Double(min(status.current, status.total)), total: Double(status.total))
                    } else {
                        ProgressView()
                    }
                    Text(progress).font(.caption).foregroundStyle(.secondary)
                }
                if let status = model.sourceIndexStatuses[SavedFolder.canonicalPath(source.path)], let last = status.lastIndexedAt {
                    Text(L10n.format("Последняя синхронизация: %@", language: model.language, last))
                        .font(.caption2).foregroundStyle(.tertiary)
                }
                if let errors = model.indexingIssues[SavedFolder.canonicalPath(source.path)], !errors.isEmpty {
                    DisclosureGroup(L10n.format("Проблемы обработки: %d", language: model.language, errors.count)) {
                        ForEach(errors) { issue in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(issue.documentID).font(.caption).textSelection(.enabled)
                                Text(model.issueMessage(issue.code)).font(.caption).foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .font(.caption)
                }
            }
            Spacer()
            Menu {
                Button(model.text("Проверить изменения"), systemImage: "arrow.clockwise") {
                    model.syncFolder(at: source.path)
                }
                if model.canCancelIndexing(at: source.path) {
                    Button(model.text("Остановить обработку"), systemImage: "stop.circle") {
                        if let folder = model.folders.first(where: { SavedFolder.path(of: $0) == source.path }) {
                            model.cancelIndexing(for: folder)
                        }
                    }
                }
                if source.available == false {
                    Button(model.text("Подключить папку снова…"), systemImage: "folder.badge.plus") {
                        model.isImportingFolders = true
                    }
                }
                Divider()
                Button(model.text("Удалить"), systemImage: "minus.circle", role: .destructive) {
                    remove()
                }
            } label: {
                Image(systemName: "ellipsis")
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(.borderless)
            .help(model.text("Действия с папкой"))
        }
        .padding(.vertical, 8)
    }

    private var stateSymbol: String {
        switch model.stateLabel(for: source) {
        case model.text("Индекс актуален"): "checkmark.circle.fill"
        case model.text("Готово с предупреждениями"), model.text("Ошибка индексации"): "exclamationmark.triangle.fill"
        case model.text("Источник недоступен"): "externaldrive.badge.minus"
        case model.text("В очереди"): "clock"
        case model.text("Индексация…"), model.text("Поиск документов…"), model.text("Останавливаем обработку…"): "arrow.triangle.2.circlepath"
        default: "circle"
        }
    }

    private var stateColor: Color {
        switch model.stateLabel(for: source) {
        case model.text("Индекс актуален"): .green
        case model.text("Готово с предупреждениями"), model.text("Ошибка индексации"), model.text("Источник недоступен"): .orange
        default: .secondary
        }
    }
}

struct SettingsPanel: View {
    @EnvironmentObject private var model: StudyAgentModel
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast
    @State private var showingDiagnostics = false

    var body: some View {
        Form {
            Section(model.text("Локальная языковая модель")) {
                if !model.modelNames.isEmpty {
                    Picker(model.text("Установленная модель"), selection: $model.modelName) {
                        Text(model.text("Без генерации ответа")).tag("")
                        if !model.modelName.isEmpty && !model.modelNames.contains(model.modelName) {
                            Text(model.modelName + " — " + model.text("Недоступен")).tag(model.modelName)
                        }
                        ForEach(model.modelNames, id: \.self) { name in
                            Text(name).tag(name)
                        }
                    }
                }
                HStack {
                    Button(model.text("Обновить список моделей"), systemImage: "arrow.clockwise") {
                        model.refreshModels()
                    }
                    Button(model.text("Сохранить модель"), systemImage: "checkmark") {
                        model.saveModel()
                    }
                    .buttonStyle(.borderedProminent)
                }
                Text(model.modelStatus)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Section(model.text("Поиск по материалам")) {
                Picker(model.text("Режим поиска"), selection: $model.searchMode) {
                    ForEach(SearchMode.allCases) { mode in
                        Text(mode.title(language: model.language)).tag(mode)
                    }
                }
                Picker(model.text("Embedding-модель"), selection: $model.embeddingModelName) {
                    Text(model.text("Не выбрана")).tag("")
                    if !model.embeddingModelName.isEmpty && !model.embeddingModels.contains(where: { $0.name == model.embeddingModelName }) {
                        Text(model.embeddingModelName + " — " + model.text("Недоступен")).tag(model.embeddingModelName)
                    }
                    ForEach(model.embeddingModels) { item in
                        Text("\(item.name) (\(item.dimensions))").tag(item.name)
                    }
                }
                Text(model.embeddingModelStatus)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                DisclosureGroup(model.text("Префиксы embedding-модели")) {
                    TextField(model.text("Префикс документов"), text: $model.documentPrefix)
                    TextField(model.text("Префикс запросов"), text: $model.queryPrefix)
                    Text(model.text("Оставьте пустыми, если модель не требует префиксов. Используйте значения из документации выбранной модели."))
                        .font(.caption).foregroundStyle(.secondary)
                }
                Button(model.text("Подготовить семантический индекс"), systemImage: "sparkle.magnifyingglass") {
                    model.prepareSemanticIndex()
                }
                .disabled(!model.hasEmbeddingProfile || model.folders.isEmpty)
                if model.semanticIndexNeedsPreparation {
                    Text(model.text("Профиль изменён. Подготовьте индекс для подключённых папок; прогресс отображается в библиотеке."))
                        .font(.callout).foregroundStyle(.orange)
                }
                Text(model.text("Поиск по смыслу и гибридный поиск требуют выбранной embedding-модели. После её выбора подготовьте индекс. Эмбеддинги обновляются при добавлении папки и проверке изменений."))
                    .font(.caption).foregroundStyle(.secondary)
            }

            Section(model.text("Внешний вид и доступность")) {
                Picker(model.text("Цветовая тема"), selection: $model.theme) {
                    ForEach(AppTheme.allCases) { theme in
                        Text(theme.title(language: model.language)).tag(theme)
                    }
                }
                Picker(model.text("Язык интерфейса"), selection: $model.language) {
                    ForEach(AppLanguage.allCases) { language in
                        Text(language.displayName).tag(language)
                    }
                }
                Toggle(model.text("Повышенный контраст"), isOn: $model.highContrast)
                    .toggleStyle(.switch)
                Toggle(model.text("Уменьшить движение"), isOn: $model.reduceMotion)
                    .toggleStyle(.switch)
            }

            Section(model.text("Конфиденциальность")) {
                Label {
                    Text(model.text("Поиск выполняется локально. Вопрос и найденные выдержки передаются только в Ollama на этом компьютере."))
                } icon: {
                    Image(systemName: "lock.shield")
                }
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }

            Section(model.text("Компоненты и диагностика")) {
                Button(model.text("Открыть настройку и диагностику…"), systemImage: "stethoscope") {
                    showingDiagnostics = true
                }
                Text(model.text("Проверка не меняет установленные компоненты. Загрузки запускаются только после вашего выбора."))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }

            Section(model.text("Знакомство")) {
                Button(model.text("Пройти знакомство ещё раз"), systemImage: "sparkles") {
                    model.replayWelcome()
                }
            }
        }
        .formStyle(.grouped)
        .sheet(isPresented: $showingDiagnostics) {
            SetupWizard()
                .environmentObject(model)
                .frame(minWidth: 680, minHeight: 530)
        }
        .contrast(model.highContrast || colorSchemeContrast == .increased ? 1.18 : 1.0)
        .padding(20)
        .navigationTitle(model.text("Настройки"))
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button(model.text("Обновить модели"), systemImage: "arrow.clockwise") {
                    model.refreshModels()
                }
            }
        }
    }
}

private struct PageHeading: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.largeTitle.weight(.semibold))
            Text(subtitle)
                .font(.title3)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
