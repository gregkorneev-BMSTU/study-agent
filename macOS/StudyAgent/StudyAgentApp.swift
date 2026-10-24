import AppKit
import SwiftUI

@main
struct StudyAgentApp: App {
    @NSApplicationDelegateAdaptor(StudyAgentAppDelegate.self) private var appDelegate
    @StateObject private var model = StudyAgentModel()

    var body: some Scene {
        WindowGroup("Study Agent", id: "main") {
            ContentView()
                .environmentObject(model)
                .preferredColorScheme(model.theme.colorScheme)
                .frame(minWidth: 760, minHeight: 560)
        }
        .commands {
            StudyAgentCommands(model: model)
        }

        Settings {
            SettingsPanel()
                .environmentObject(model)
                .preferredColorScheme(model.theme.colorScheme)
                .frame(minWidth: 520, minHeight: 560)
        }
        .defaultSize(width: 600, height: 760)
        .windowResizability(.contentSize)

        MenuBarExtra("Study Agent", systemImage: "text.book.closed") {
            MenuBarMenu()
                .environmentObject(model)
        }
        .menuBarExtraStyle(.menu)
    }
}

final class StudyAgentAppDelegate: NSObject, NSApplicationDelegate {
    private var windowObserver: NSObjectProtocol?

    func applicationDidFinishLaunching(_ notification: Notification) {
        windowObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.didBecomeKeyNotification,
            object: nil,
            queue: .main
        ) { _ in
            AppWindowTransparency.applySavedValue()
        }
        localizeMenus()
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        AppWindowTransparency.applySavedValue()
        localizeMenus()
    }

    deinit {
        if let windowObserver {
            NotificationCenter.default.removeObserver(windowObserver)
        }
    }

    private func localizeMenus() {
        let language = UserDefaults.standard.string(forKey: "general/language")
            .flatMap(AppLanguage.init(rawValue:)) ?? .systemDefault
        MenuBarLocalization.apply(language)
    }
}

enum AppWindowTransparency {
    static let defaultsKey = "appearance.windowTransparency"
    static let minimum = 0.35

    static func apply(_ value: Double) {
        let alpha = min(max(value, minimum), 1.0)
        for window in NSApp.windows where window.alphaValue != alpha {
            window.alphaValue = alpha
        }
    }

    static func applySavedValue() {
        let alpha = UserDefaults.standard.object(forKey: defaultsKey) as? Double ?? 1.0
        apply(alpha)
    }
}

private struct MenuBarMenu: View {
    @EnvironmentObject private var model: StudyAgentModel
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Button(model.text("Открыть Study Agent")) {
            NSApp.activate(ignoringOtherApps: true)
            openWindow(id: "main")
        }
        SettingsLink {
            Text(model.text("Настройки…"))
        }
        Divider()
        Button(model.text("Завершить Study Agent")) {
            NSApp.terminate(nil)
        }
    }
}

private struct StudyAgentCommands: Commands {
    @ObservedObject var model: StudyAgentModel

    var body: some Commands {
        CommandGroup(replacing: .appInfo) {
            Button(model.text("Об Study Agent")) {
                let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—"
                let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "—"
                let github = NSAttributedString(
                    string: "github.com/gregkorneev",
                    attributes: [.link: URL(string: "https://github.com/gregkorneev")!]
                )
                NSApp.orderFrontStandardAboutPanel(options: [
                    .applicationName: "Study Agent",
                    .applicationVersion: version,
                    .version: build,
                    .credits: github,
                ])
            }
        }
        CommandGroup(replacing: .appSettings) {
            SettingsLink {
                Text(model.text("Настройки…"))
            }
        }
        CommandGroup(after: .newItem) {
            Button(model.text("Добавить папку…")) {
                model.isImportingFolders = true
            }
            .keyboardShortcut("o", modifiers: .command)
        }
        CommandGroup(after: .textEditing) {
            Button(model.text("Поиск по материалам")) {
                model.selectedSection = .search
                NSApp.activate(ignoringOtherApps: true)
            }
            .keyboardShortcut("f", modifiers: .command)
        }
        CommandGroup(after: .help) {
            Button(model.text("Пройти знакомство ещё раз"), systemImage: "sparkles") {
                NSApp.activate(ignoringOtherApps: true)
                openWindow(id: "main")
                model.replayWelcome()
            }
        }
    }

    @Environment(\.openWindow) private var openWindow
}

enum MenuBarLocalization {
    private static let menuTitles = [
        "Файл", "Правка", "Вид", "Окно", "Справка",
    ]

    static func apply(_ language: AppLanguage) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
            let items = NSApp.mainMenu?.items ?? []
            for item in items {
                guard let source = menuTitles.first(where: {
                    $0 == item.title || L10n.text($0, language: .english) == item.title
                }) else {
                    continue
                }
                item.title = L10n.text(source, language: language)
            }
        }
    }
}
