import AppKit
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
                model.searchStatus = model.text(error.localizedDescription)
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
                    if let answer = model.answerText {
                        GroupBox(model.text("Ответ")) {
                            Text(answer)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .textSelection(.enabled)
                                .padding(.top, 4)
                        }
                    }
                    ForEach(model.hits.indices, id: \.self) { index in
                        let hit = model.hits[index]
                        Button {
                            model.open(hit)
                        } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack(alignment: .firstTextBaseline) {
                                    Text("[\(index + 1)]  \(hit.title)")
                                        .font(.headline)
                                    Spacer()
                                    Image(systemName: "arrow.up.forward.square")
                                        .font(.caption)
                                }
                                Text("\(URL(filePath: hit.sourceRoot).lastPathComponent)/\(hit.documentID)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(hit.excerpt)
                                    .font(.body)
                                    .foregroundStyle(.primary)
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .padding(14)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(.background, in: RoundedRectangle(cornerRadius: 12))
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint(model.text("Открыть исходный документ"))
                    }
                }
            }
        }
        .padding(28)
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
        HStack(spacing: 14) {
            Image(systemName: "folder.fill")
                .font(.title2)
                .foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 4) {
                Text(source.name).font(.headline)
                Text(L10n.format("%d файлов поддерживаемых форматов", language: model.language, source.documentCount))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button(model.text("Удалить"), systemImage: "minus.circle") {
                remove()
            }
            .labelStyle(.iconOnly)
            .buttonStyle(.borderless)
            .help(model.text("Отключить папку от библиотеки"))
        }
        .padding(.vertical, 8)
    }
}

struct SettingsPanel: View {
    @EnvironmentObject private var model: StudyAgentModel
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @State private var showingDiagnostics = false

    var body: some View {
        Form {
            Section(model.text("Локальная языковая модель")) {
                if !model.modelNames.isEmpty {
                    Picker(model.text("Установленная модель"), selection: $model.modelName) {
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

            Section(model.text("Liquid Glass")) {
                Text(model.text("Study Agent оставляет оформление боковой панели и панели инструментов macOS. На поддерживаемых версиях macOS система отображает их как Liquid Glass. Публичные API Apple не дают приложению отдельный числовой регулятор интенсивности этих системных материалов."))
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if reduceTransparency {
                    Label(
                        model.text("В macOS включено «Уменьшить прозрачность». Это системное ограничение имеет приоритет."),
                        systemImage: "accessibility"
                    )
                    .font(.callout)
                    .fixedSize(horizontal: false, vertical: true)
                }

                if #available(macOS 27, *) {
                    Text(model.text("В macOS 27 выберите прозрачность Liquid Glass в разделе «Внешний вид» системных настроек."))
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                } else if #available(macOS 26.1, *) {
                    Text(model.text("В macOS 26.1 и новее оформление Liquid Glass выбирается в разделе «Внешний вид» системных настроек."))
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    Text(model.text("Системное оформление Liquid Glass настраивается в macOS, когда эта возможность доступна."))
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Button(model.text("Открыть настройки macOS…"), systemImage: "gearshape") {
                    if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.systempreferences") {
                        NSWorkspace.shared.open(url)
                    }
                }
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
