import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject private var model: StudyAgentModel

    private static let sidebarLogo: NSImage? = {
        guard let url = Bundle.main.url(forResource: "AppIcon_1024", withExtension: "png") else {
            return nil
        }
        return NSImage(contentsOf: url)
    }()

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                HStack(spacing: 10) {
                    if let logo = Self.sidebarLogo {
                        Image(nsImage: logo)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 30, height: 30)
                            .accessibilityHidden(true)
                    }
                    Text("Study Agent")
                        .font(.headline)
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)

                List(selection: $model.selectedSection) {
                    ForEach(MainSection.allCases) { section in
                        Label(section.title, systemImage: section.symbol)
                            .tag(section)
                    }
                }
                .listStyle(.sidebar)
                .modifier(HighContrast(enabled: model.highContrast))

                Label(model.ollamaStatus, systemImage: "circle.fill")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .accessibilityLabel(model.ollamaStatus)
            }
            .frame(minWidth: 180, idealWidth: 220, maxWidth: 260)

            Group {
                switch model.selectedSection {
                case .search:
                    SearchPanel()
                case .library:
                    LibraryPanel()
                case .settings:
                    SettingsPanel()
                }
            }
            .frame(minWidth: 520, maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .modifier(HighContrast(enabled: model.highContrast))
        }
        .frame(minWidth: 760, minHeight: 560)
        .modifier(AdaptiveToolbarBackground(reduceTransparency: model.reduceTransparency))
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                if model.selectedSection == .library {
                    Button("Добавить папку", systemImage: "folder.badge.plus") {
                        model.isImportingFolders = true
                    }
                    .help("Добавить папку с учебными материалами")
                }
            }
            ToolbarItem(placement: .automatic) {
                SettingsLink {
                    Label("Настройки", systemImage: "gearshape")
                }
                .help("Настройки Study Agent")
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
                model.searchStatus = error.localizedDescription
            }
        }
        .task {
            model.refreshSources()
            model.refreshModels()
        }
        .animation(model.reduceMotion ? nil : .easeOut(duration: 0.15), value: model.selectedSection)
    }
}

private struct HighContrast: ViewModifier {
    let enabled: Bool

    @ViewBuilder
    func body(content: Content) -> some View {
        if enabled {
            content.contrast(1.18)
        } else {
            content
        }
    }
}

private struct SearchPanel: View {
    @EnvironmentObject private var model: StudyAgentModel

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            PageHeading(
                title: "Поиск по материалам",
                subtitle: "Ответы строятся локальной моделью по выбранным источникам."
            )

            HStack(spacing: 12) {
                TextField("Спросите о лекциях, конспектах или учебниках…", text: $model.query)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(model.search)
                    .accessibilityLabel("Вопрос по учебным материалам")
                Button {
                    model.search()
                } label: {
                    if model.isSearching {
                        ProgressView().controlSize(.small)
                    } else {
                        Label("Спросить", systemImage: "arrow.up.circle.fill")
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
                        GroupBox("Ответ") {
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
                        .accessibilityHint("Открыть исходный документ")
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
                title: "Библиотека",
                subtitle: "Подключайте только те папки, которые хотите искать. Файлы не покидают этот компьютер."
            )

            if model.sourceSummaries.isEmpty {
                ContentUnavailableView {
                    Label("Папки пока не добавлены", systemImage: "folder.badge.plus")
                } description: {
                    Text("Добавьте папку с файлами Markdown или TXT.")
                } actions: {
                    Button("Добавить папку…", systemImage: "folder.badge.plus") {
                        model.isImportingFolders = true
                    }
                    .buttonStyle(.borderedProminent)
                }
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

            Spacer(minLength: 0)
        }
        .padding(28)
        .foregroundStyle(Color(nsColor: .labelColor))
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button("Добавить папку", systemImage: "folder.badge.plus") {
                    model.isImportingFolders = true
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }
}

private struct SourceRow: View {
    let source: SourceSummary
    let remove: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "folder.fill")
                .font(.title2)
                .foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 4) {
                Text(source.name).font(.headline)
                Text("\(source.documentCount) файлов Markdown и TXT")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("Удалить", systemImage: "minus.circle") {
                remove()
            }
            .labelStyle(.iconOnly)
            .buttonStyle(.borderless)
            .help("Отключить папку от библиотеки")
        }
        .padding(.vertical, 8)
    }
}

struct SettingsPanel: View {
    @EnvironmentObject private var model: StudyAgentModel

    var body: some View {
        Form {
            Section("Локальная языковая модель") {
                TextField("Тег модели Ollama", text: $model.modelName)
                    .textFieldStyle(.roundedBorder)
                if !model.modelNames.isEmpty {
                    Picker("Установленная модель", selection: $model.modelName) {
                        ForEach(model.modelNames, id: \.self) { name in
                            Text(name).tag(name)
                        }
                    }
                }
                HStack {
                    Button("Обновить список моделей", systemImage: "arrow.clockwise") {
                        model.refreshModels()
                    }
                    Button("Сохранить модель", systemImage: "checkmark") {
                        model.saveModel()
                    }
                    .buttonStyle(.borderedProminent)
                }
                Text(model.modelStatus)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Section("Внешний вид и доступность") {
                Picker("Цветовая тема", selection: $model.theme) {
                    ForEach(AppTheme.allCases) { theme in
                        Text(theme.title).tag(theme)
                    }
                }
                Toggle("Уменьшить прозрачность поверхностей", isOn: $model.reduceTransparency)
                    .toggleStyle(.switch)
                Toggle("Повышенный контраст", isOn: $model.highContrast)
                    .toggleStyle(.switch)
                Toggle("Уменьшить движение", isOn: $model.reduceMotion)
                    .toggleStyle(.switch)
            }

            Section("Конфиденциальность") {
                Label {
                    Text("Поиск выполняется локально. Вопрос и найденные выдержки передаются только в Ollama на этом компьютере.")
                } icon: {
                    Image(systemName: "lock.shield")
                }
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }
        }
        .formStyle(.grouped)
        .contrast(model.highContrast ? 1.18 : 1.0)
        .padding(20)
        .navigationTitle("Настройки")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button("Обновить модели", systemImage: "arrow.clockwise") {
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

private struct AdaptiveToolbarBackground: ViewModifier {
    let reduceTransparency: Bool

    @ViewBuilder
    func body(content: Content) -> some View {
        if reduceTransparency {
            content.toolbarBackground(Color(nsColor: .windowBackgroundColor), for: .windowToolbar)
        } else {
            content.toolbarBackground(.automatic, for: .windowToolbar)
        }
    }
}
