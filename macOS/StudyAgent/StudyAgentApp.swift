import SwiftUI

@main
struct StudyAgentApp: App {
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
                .frame(width: 520, height: 560)
        }

        MenuBarExtra("Study Agent", systemImage: "text.book.closed") {
            MenuBarMenu()
                .environmentObject(model)
        }
        .menuBarExtraStyle(.menu)
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
                NSApp.orderFrontStandardAboutPanel(options: [
                    .applicationName: "Study Agent",
                    .applicationVersion: "0.1.0",
                    .version: "1",
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
    }
}
