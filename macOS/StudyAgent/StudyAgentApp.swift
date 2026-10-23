import AppKit
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
        }
        .menuBarExtraStyle(.menu)
    }
}

private struct MenuBarMenu: View {
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Button("Открыть Study Agent") {
            NSApp.activate(ignoringOtherApps: true)
            openWindow(id: "main")
        }
        SettingsLink {
            Text("Настройки…")
        }
        Divider()
        Button("Завершить Study Agent") {
            NSApp.terminate(nil)
        }
    }
}

private struct StudyAgentCommands: Commands {
    @ObservedObject var model: StudyAgentModel

    var body: some Commands {
        CommandGroup(replacing: .appSettings) {
            SettingsLink {
                Text("Настройки…")
            }
        }
        CommandGroup(after: .newItem) {
            Button("Добавить папку…") {
                model.isImportingFolders = true
            }
            .keyboardShortcut("o", modifiers: .command)
        }
        CommandGroup(after: .textEditing) {
            Button("Поиск по материалам") {
                model.selectedSection = .search
                NSApp.activate(ignoringOtherApps: true)
            }
            .keyboardShortcut("f", modifiers: .command)
        }
    }
}
