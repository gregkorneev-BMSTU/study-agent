import Foundation
import Darwin

enum MenuBarLocalization {
    static func apply(_ language: AppLanguage) {}
}

@main
struct ModelQueueTest {
    @MainActor
    static func main() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let folder = root.appendingPathComponent("notes")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let backend = root.appendingPathComponent("backend.py")
        let log = root.appendingPathComponent("calls.txt")
        try """
        #!/usr/bin/env python3
        import json
        import os
        import sys

        request = json.loads(sys.stdin.readline())
        command = request["command"]
        with open(os.environ["STUDY_AGENT_TEST_LOG"], "a+", encoding="utf-8") as file:
            file.seek(0)
            count = sum(line.strip() == command for line in file)
            file.write(command + "\\n")
        if command == "list_sources":
            result = {"sources": []}
        elif command in ("index_source", "remove_index_source") and count == 0:
            print(json.dumps({"ok": False, "error": {"message": "temporary failure"}}))
            sys.exit(0)
        else:
            result = {}
        print(json.dumps({"ok": True, "result": result}))
        """.write(to: backend, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: backend.path)
        setenv("STUDY_AGENT_BACKEND_EXECUTABLE", backend.path, 1)
        setenv("STUDY_AGENT_TEST_LOG", log.path, 1)

        let defaults = UserDefaults.standard
        let keys = ["library.bookmarks.v1", "library.pending_removals.v1"]
        let previous = keys.map { defaults.object(forKey: $0) }
        defer {
            for (key, value) in zip(keys, previous) {
                if let value { defaults.set(value, forKey: key) }
                else { defaults.removeObject(forKey: key) }
            }
        }
        keys.forEach(defaults.removeObject(forKey:))
        let model = StudyAgentModel()
        model.addFolders([folder])
        try await wait { model.hasFailedLibraryOperations }
        model.retryFailedLibraryOperations()
        try await wait { calls("index_source", in: log) == 2 && !model.hasFailedLibraryOperations }

        model.removeFolder(at: SavedFolder.canonicalPath(folder.path))
        try await wait { model.hasFailedLibraryOperations }
        model.retryFailedLibraryOperations()
        try await wait { calls("remove_index_source", in: log) == 2 && !model.hasFailedLibraryOperations }
    }

    @MainActor
    private static func wait(_ condition: () -> Bool) async throws {
        for _ in 0..<100 {
            if condition() { return }
            try await Task.sleep(for: .milliseconds(50))
        }
        fatalError("Timed out waiting for library operation")
    }

    private static func calls(_ command: String, in log: URL) -> Int {
        let text = (try? String(contentsOf: log, encoding: .utf8)) ?? ""
        return text.split(separator: "\n").filter { $0 == command }.count
    }
}
