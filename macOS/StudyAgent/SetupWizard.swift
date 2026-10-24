import AppKit
import Foundation
import SwiftUI

private enum SetupStep: Int, CaseIterable {
    case welcome, diagnostics, components, installation, finish

    var symbol: String {
        switch self {
        case .welcome: "sparkles"
        case .diagnostics: "stethoscope"
        case .components: "square.stack.3d.up"
        case .installation: "arrow.down.circle"
        case .finish: "checkmark.circle"
        }
    }
}

private struct SetupSnapshot {
    var macOS: String = "—"
    var architecture: String = "—"
    var memory: String = "—"
    var disk: String = "—"
    var diskBytes: Int64?
    var osSupported = true
    var backend: String = "—"
    var pdf: String = "—"
    var ocr: String = "—"
    var ocrRuntimeAvailable = false
    var ocrWeightsInstalled = false
    var internet: String = "—"
    var ollama: String = "—"
    var ollamaAppURL: URL?
    var ollamaRunning = false
    var models: [String] = []
}

@MainActor
private final class SetupController: ObservableObject {
    @Published var snapshot = SetupSnapshot()
    @Published var checking = false
    @Published var pulling = false
    @Published var pullStatus = ""
    @Published var pullFraction: Double?
    @Published var installingOCR = false
    @Published var ocrFraction: Double?
    @Published var ocrDownloadStatus = ""
    @Published var error: String?

    private var pullTask: Task<Void, Never>?
    private var ocrTask: Task<Void, Never>?
    private let ollamaBase = URL(string: "http://127.0.0.1:11434")!

    func diagnose(using model: StudyAgentModel) {
        guard !checking else { return }
        checking = true
        error = nil
        Task {
            var result = SetupSnapshot()
            let os = ProcessInfo.processInfo.operatingSystemVersion
            result.macOS = "macOS \(os.majorVersion).\(os.minorVersion).\(os.patchVersion)"
            result.osSupported = os.majorVersion >= 14
            #if arch(arm64)
            result.architecture = "Apple silicon (arm64)"
            #else
            result.architecture = "Intel (x86_64)"
            #endif
            result.memory = ByteCountFormatter.string(
                fromByteCount: Int64(ProcessInfo.processInfo.physicalMemory), countStyle: .memory
            )
            if let values = try? FileManager.default.homeDirectoryForCurrentUser
                .resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]),
               let bytes = values.volumeAvailableCapacityForImportantUsage {
                result.diskBytes = Int64(bytes)
                result.disk = ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
            }
            do {
                let health = try await model.diagnoseBackend()
                result.backend = health["backend_healthy"] as? Bool == true
                    ? model.text("Работает") : model.text("Недоступен")
                result.pdf = health["pdf_available"] as? Bool == true
                    ? model.text("Доступен") : model.text("Недоступен")
                result.ocr = health["ocr_runtime_available"] as? Bool == true
                    ? model.text("Среда доступна; веса не установлены")
                    : model.text("Не установлен (необязательно)")
                result.ocrRuntimeAvailable = health["ocr_runtime_available"] as? Bool == true
                result.ocrWeightsInstalled = health["ocr_weights_state"] as? String == "installed"
                if result.ocrWeightsInstalled {
                    result.ocr = model.text("Готов к работе")
                }
            } catch {
                result.backend = model.text("Недоступен")
                result.pdf = "—"
                result.ocr = model.text("Не удалось проверить")
                self.error = model.text(error.localizedDescription)
            }
            result.ollamaAppURL = findOllamaApp()
            do {
                let request = URLRequest(url: ollamaBase.appending(path: "api/tags"),
                                         cachePolicy: .reloadIgnoringLocalCacheData,
                                         timeoutInterval: 3)
                let (data, response) = try await URLSession.shared.data(for: request)
                guard (response as? HTTPURLResponse)?.statusCode == 200,
                      let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let models = json["models"] as? [[String: Any]] else {
                    throw URLError(.badServerResponse)
                }
                result.ollamaRunning = true
                result.models = models.compactMap { $0["name"] as? String }
                result.ollama = model.text("Работает")
            } catch {
                result.ollama = result.ollamaAppURL == nil
                    ? model.text("Не найдена") : model.text("Установлена, но не отвечает")
            }
            do {
                var request = URLRequest(url: URL(string: "https://ollama.com/download")!,
                                         cachePolicy: .reloadIgnoringLocalCacheData,
                                         timeoutInterval: 5)
                request.httpMethod = "HEAD"
                let (_, response) = try await URLSession.shared.data(for: request)
                result.internet = ((response as? HTTPURLResponse)?.statusCode ?? 0) < 400
                    ? model.text("Доступен") : model.text("Недоступен")
            } catch {
                result.internet = model.text("Недоступен")
            }
            snapshot = result
            checking = false
        }
    }

    func openOllamaDownload() {
        NSWorkspace.shared.open(URL(string: "https://ollama.com/download")!)
    }

    func openInstalledOllama(using model: StudyAgentModel) {
        guard let url = snapshot.ollamaAppURL else { return }
        NSWorkspace.shared.openApplication(at: url, configuration: NSWorkspace.OpenConfiguration()) { _, error in
            Task { @MainActor in
                if let error { self.error = model.text(error.localizedDescription) }
                self.diagnose(using: model)
            }
        }
    }

    func pullQwen(using model: StudyAgentModel) {
        guard snapshot.ollamaRunning, !pulling else { return }
        let tag = "qwen3.5:4b"
        if snapshot.models.contains(where: { $0 == tag || $0 == "qwen3.5:latest" }) {
            pullStatus = model.text("Модель уже установлена")
            return
        }
        pulling = true
        error = nil
        pullFraction = nil
        pullStatus = model.text("Подключение к локальному Ollama…")
        pullTask = Task {
            do {
                var request = URLRequest(url: ollamaBase.appending(path: "api/pull"))
                request.httpMethod = "POST"
                request.timeoutInterval = 3600
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONSerialization.data(withJSONObject: ["model": tag, "stream": true])
                let (bytes, response) = try await URLSession.shared.bytes(for: request)
                guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                    throw URLError(.badServerResponse)
                }
                var completedSuccessfully = false
                for try await line in bytes.lines {
                    try Task.checkCancellation()
                    guard let data = line.data(using: .utf8),
                          let event = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                        continue
                    }
                    if let serverError = event["error"] as? String {
                        throw SetupError.message(serverError)
                    }
                    if let status = event["status"] as? String {
                        pullStatus = status
                        if status == "success" { completedSuccessfully = true }
                    }
                    if let completed = event["completed"] as? Double,
                       let total = event["total"] as? Double, total > 0 {
                        pullFraction = min(1, max(0, completed / total))
                    }
                }
                guard completedSuccessfully else { throw URLError(.networkConnectionLost) }
                pullStatus = model.text("Загрузка завершена")
                diagnose(using: model)
                model.refreshModels()
            } catch is CancellationError {
                pullStatus = model.text("Загрузка отменена")
            } catch {
                self.error = model.text(error.localizedDescription)
            }
            pulling = false
            pullTask = nil
        }
    }

    func cancelPull() {
        pullTask?.cancel()
    }

    func installOCR(using model: StudyAgentModel) {
        guard !installingOCR, snapshot.ocrRuntimeAvailable else { return }
        installingOCR = true
        ocrFraction = nil
        ocrDownloadStatus = model.text("Подготовка загрузки Chandra…")
        error = nil
        ocrTask = Task {
            do {
                _ = try await model.installOCRModel { event in
                    Task { @MainActor in
                        guard let current = event["current"] as? Double,
                              let total = event["total"] as? Double, total > 0 else { return }
                        self.ocrFraction = min(1, max(0, current / total))
                        self.ocrDownloadStatus = event["description"] as? String
                            ?? model.text("Загружается Chandra OCR…")
                    }
                }
                snapshot.ocrWeightsInstalled = true
                snapshot.ocr = model.text("Готов к работе")
                ocrDownloadStatus = model.text("Загрузка завершена")
            } catch is CancellationError {
                ocrDownloadStatus = model.text("Загрузка отменена")
            } catch {
                self.error = model.text("Не удалось загрузить Chandra OCR. Проверьте интернет и свободное место, затем повторите попытку.")
            }
            installingOCR = false
            ocrTask = nil
        }
    }

    func cancelOCRDownload() {
        ocrTask?.cancel()
    }

    private func findOllamaApp() -> URL? {
        let candidates = [
            URL(fileURLWithPath: "/Applications/Ollama.app"),
            FileManager.default.homeDirectoryForCurrentUser.appending(path: "Applications/Ollama.app")
        ]
        return candidates.first { FileManager.default.fileExists(atPath: $0.path) }
            ?? NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.electron.ollama")
    }
}

private enum SetupError: LocalizedError {
    case message(String)
    var errorDescription: String? {
        switch self { case .message(let message): message }
    }
}

struct SetupWizard: View {
    @EnvironmentObject private var model: StudyAgentModel
    @StateObject private var controller = SetupController()
    @State private var step: SetupStep = .welcome

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                Label(model.text("Подготовка Study Agent"), systemImage: "graduationcap")
                    .font(.title2.weight(.semibold))
                Spacer()
                Text("\(step.rawValue + 1) / 5")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            HStack(spacing: 12) {
                ForEach(SetupStep.allCases, id: \.rawValue) { item in
                    Image(systemName: item.symbol)
                        .foregroundStyle(item.rawValue <= step.rawValue ? Color.accentColor : .secondary)
                        .accessibilityLabel(model.text(title(for: item)))
                    if item != .finish { Rectangle().fill(.quaternary).frame(height: 1) }
                }
            }
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(model.text(title(for: step))).font(.title.weight(.semibold))
                    content
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            if let error = controller.error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red)
                    .font(.callout)
            }
            Divider()
            HStack {
                Button(model.text("Назад")) { step = SetupStep(rawValue: step.rawValue - 1) ?? .welcome }
                    .disabled(step == .welcome || controller.pulling)
                Spacer()
                if step == .finish {
                    Button(model.text("Открыть Study Agent")) { model.finishSetup() }
                        .buttonStyle(.borderedProminent)
                } else {
                    Button(model.text("Продолжить")) {
                        step = SetupStep(rawValue: step.rawValue + 1) ?? .finish
                        if step == .diagnostics { controller.diagnose(using: model) }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(controller.pulling || (step == .diagnostics && controller.checking))
                }
            }
        }
        .padding(26)
        .onDisappear {
            controller.cancelPull()
            controller.cancelOCRDownload()
        }
    }

    @ViewBuilder private var content: some View {
        switch step {
        case .welcome:
            Image(nsImage: NSApp.applicationIconImage)
                .resizable()
                .frame(width: 88, height: 88)
                .accessibilityHidden(true)
            Text(model.text("Study Agent ищет по выбранным папкам и готовит ответы на вашем Mac. Мастер проверит необходимые компоненты. Загрузки начинаются только после вашего согласия."))
            Label(model.text("Ваши документы остаются на этом компьютере."), systemImage: "lock.shield")
                .foregroundStyle(.secondary)
            if Bundle.main.bundleURL.path.hasPrefix("/Volumes/") {
                Label(model.text("Перетащите Study Agent в «Программы» перед настройкой."), systemImage: "externaldrive")
                    .foregroundStyle(.orange)
                Button(model.text("Открыть «Программы»")) {
                    NSWorkspace.shared.open(URL(fileURLWithPath: "/Applications"))
                }
            }
        case .diagnostics:
            if controller.checking { ProgressView(model.text("Проверка компонентов…")) }
            diagnosticRow("macOS", controller.snapshot.macOS)
            diagnosticRow(model.text("Процессор"), controller.snapshot.architecture)
            diagnosticRow(model.text("Память"), controller.snapshot.memory)
            diagnosticRow(model.text("Свободное место"), controller.snapshot.disk)
            diagnosticRow(model.text("Встроенный backend"), controller.snapshot.backend)
            diagnosticRow("PDF", controller.snapshot.pdf)
            diagnosticRow(model.text("Доступ к сайту Ollama"), controller.snapshot.internet)
            if !controller.snapshot.osSupported {
                Label(model.text("Требуется macOS 14 или новее."), systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
            }
            if let bytes = controller.snapshot.diskBytes, bytes < 4_000_000_000 {
                Label(model.text("Для Qwen 3.5 4B может не хватить свободного места."), systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
            }
            Button(model.text("Проверить снова"), systemImage: "arrow.clockwise") {
                controller.diagnose(using: model)
            }.disabled(controller.checking)
        case .components:
            diagnosticRow("Ollama", controller.snapshot.ollama)
            diagnosticRow(model.text("Локальные модели"), controller.snapshot.models.isEmpty
                          ? model.text("Не найдены") : controller.snapshot.models.joined(separator: ", "))
            if !controller.snapshot.models.isEmpty {
                Picker(model.text("Модель для ответов"), selection: $model.modelName) {
                    ForEach(controller.snapshot.models, id: \.self) { name in
                        Text(name).tag(name)
                    }
                }
                if !controller.snapshot.models.contains(model.modelName) {
                    Text(model.text("Выберите установленную модель для ответов."))
                        .foregroundStyle(.orange)
                }
            }
            diagnosticRow("Chandra OCR", controller.snapshot.ocr)
            if controller.snapshot.ocrRuntimeAvailable {
                if controller.snapshot.ocrWeightsInstalled {
                    Label(model.text("Chandra OCR готов к работе офлайн."), systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                } else if controller.installingOCR {
                    if let fraction = controller.ocrFraction { ProgressView(value: fraction) }
                    else { ProgressView() }
                    Text(controller.ocrDownloadStatus).font(.callout).foregroundStyle(.secondary)
                    Button(model.text("Отменить загрузку"), role: .cancel) {
                        controller.cancelOCRDownload()
                    }
                } else {
                    Button(model.text("Установить Chandra OCR · 10,6 ГБ"), systemImage: "arrow.down.circle") {
                        controller.installOCR(using: model)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(controller.checking || (controller.snapshot.diskBytes.map { $0 < 12_000_000_000 } ?? false))
                    if let bytes = controller.snapshot.diskBytes, bytes < 12_000_000_000 {
                        Text(model.text("Для установки Chandra требуется не менее 12 ГБ свободного места."))
                            .foregroundStyle(.orange)
                    }
                    Text(model.text("Веса загружаются с Hugging Face по вашему нажатию и сохраняются на этом Mac. Документы никуда не отправляются. Для запуска OCR требуется много оперативной памяти."))
                        .foregroundStyle(.secondary)
                    Link(model.text("Лицензия весов Chandra"), destination: URL(string: "https://huggingface.co/datalab-to/chandra-ocr-2/blob/af93b47dba1b47b6640c86ccf487ed2260ab9a09/LICENSE")!)
                }
            } else {
                Text(model.text("OCR runtime недоступен в этой сборке. Переустановите Study Agent."))
                    .foregroundStyle(.secondary)
            }
            if controller.snapshot.ollamaAppURL != nil && !controller.snapshot.ollamaRunning {
                Button(model.text("Запустить установленную Ollama"), systemImage: "play.fill") {
                    controller.openInstalledOllama(using: model)
                }
            } else if controller.snapshot.ollamaAppURL == nil {
                Button(model.text("Открыть официальный сайт Ollama"), systemImage: "arrow.up.right.square") {
                    controller.openOllamaDownload()
                }
                Text(model.text("Установите Ollama обычным способом macOS, затем вернитесь и повторите проверку."))
                    .foregroundStyle(.secondary)
            }
            Button(model.text("Проверить снова"), systemImage: "arrow.clockwise") {
                controller.diagnose(using: model)
            }.disabled(controller.checking)
        case .installation:
            Text(model.text("Рекомендуемая локальная модель: Qwen 3.5 4B. Загрузка через работающую на этом компьютере Ollama потребует примерно 3,3–4 ГБ диска. Скорость зависит от памяти и процессора."))
            if controller.snapshot.models.contains(model.modelName) {
                Label(model.text("Выбранная модель уже установлена; повторная загрузка не нужна."), systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
            }
            if controller.snapshot.models.contains("qwen3.5:4b") {
                Label(model.text("Модель уже установлена"), systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
            } else if controller.pulling {
                if let fraction = controller.pullFraction { ProgressView(value: fraction) }
                else { ProgressView() }
                Text(controller.pullStatus).font(.callout).foregroundStyle(.secondary)
                Button(model.text("Отменить загрузку"), role: .cancel) { controller.cancelPull() }
            } else {
                Button(model.text("Загрузить Qwen 3.5 4B"), systemImage: "arrow.down.circle") {
                    controller.pullQwen(using: model)
                }
                .buttonStyle(.borderedProminent)
                .disabled(!controller.snapshot.ollamaRunning ||
                          (controller.snapshot.diskBytes.map { $0 < 4_000_000_000 } ?? false))
                if !controller.pullStatus.isEmpty { Text(controller.pullStatus).foregroundStyle(.secondary) }
            }
            Text(model.text("Можно продолжить без загрузки. Поиск по материалам работает, но ответы модели требуют установленной Ollama и модели."))
                .foregroundStyle(.secondary)
        case .finish:
            Label(model.text("Настройка завершена"), systemImage: "checkmark.circle.fill")
                .font(.title3)
            Text(model.text("Добавьте папку в библиотеку и задайте вопрос. Проверку компонентов можно открыть снова в настройках."))
            if controller.snapshot.backend != model.text("Работает") {
                Label(model.text("Встроенный backend недоступен. Переустановите Study Agent для поиска по материалам."), systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
            }
            if !controller.snapshot.ollamaRunning || controller.snapshot.models.isEmpty {
                Label(model.text("Ответы локальной модели пока недоступны. Завершите установку Ollama и модели позже в настройках."), systemImage: "info.circle")
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func diagnosticRow(_ title: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).foregroundStyle(.secondary)
            Spacer(minLength: 12)
            Text(value).multilineTextAlignment(.trailing).textSelection(.enabled)
        }
        .font(.callout)
    }

    private func title(for step: SetupStep) -> String {
        switch step {
        case .welcome: "Добро пожаловать"
        case .diagnostics: "Проверка компьютера"
        case .components: "Компоненты"
        case .installation: "Локальная модель"
        case .finish: "Готово"
        }
    }
}
