import Foundation
import Darwin

enum MenuBarLocalization {
    static func apply(_ language: AppLanguage) {}
}

@main
struct ModelQueueTest {
    @MainActor
    static func main() async throws {
        let searchHits = try JSONDecoder().decode([SearchHit].self, from: Data("""
        [{"title":"lecture","document_id":"physics.pdf","excerpt":"text","score":1,"source_root":"/library","page_number":17,"heading":null,"marker":"p17","extraction_type":"pdf_text","chunk_id":"chunk-1"},
         {"title":"lecture","document_id":"physics.pdf","excerpt":"other text","score":1,"source_root":"/library","page_number":18,"heading":null,"marker":"p18","extraction_type":"pdf_text","chunk_id":"chunk-2"}]
        """.utf8))
        precondition(searchHits[0].pageNumber == 17)
        precondition(searchHits[0].chunkID == "chunk-1")
        precondition(searchHits[0].id != searchHits[1].id)

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
        elif command in ("sync_source", "remove_index_source") and count == 0:
            print(json.dumps({"request_id": request["request_id"], "ok": False, "error": {"message": "temporary failure"}}))
            sys.exit(0)
        elif command == "sync_source":
            print(json.dumps({"event": "progress", "request_id": request["request_id"], "result": {"phase": "indexing", "current": 1, "total": 1, "indexed": 1, "partial": 0, "skipped": 0, "failed": 0}}))
            result = {"cancelled": False, "failed": 0, "partial": 0, "errors": []}
        elif command == "index_status":
            result = {"source_id": "test", "documents": 1, "ready": 1, "partial": 0, "failed": 0, "chunks": 1, "last_indexed_at": "2026-10-25 10:00:00"}
        else:
            result = {}
        print(json.dumps({"request_id": request["request_id"], "ok": True, "result": result}))
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
        try await wait { calls("sync_source", in: log) == 2 && !model.hasFailedLibraryOperations }
        precondition(model.indexingStates[SavedFolder.canonicalPath(folder.path)] != nil)

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
