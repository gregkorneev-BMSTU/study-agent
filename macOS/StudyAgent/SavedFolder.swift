import Foundation
import Darwin

struct SavedFolder: Codable, Identifiable, Hashable {
    var id: UUID
    var name: String
    var bookmark: Data
    var path: String? = nil

    static func path(of folder: SavedFolder) -> String? {
        if let path = folder.path { return canonicalPath(path) }
        var stale = false
        return try? canonicalPath(URL(
            resolvingBookmarkData: folder.bookmark,
            options: [],
            relativeTo: nil,
            bookmarkDataIsStale: &stale
        ).path)
    }

    static func canonicalPath(_ path: String) -> String {
        guard let resolved = path.withCString({ realpath($0, nil) }) else { return path }
        defer { free(resolved) }
        return String(cString: resolved)
    }

    static func searchRoots(_ folders: [SavedFolder]) -> [String] {
        folders.compactMap(path(of:))
    }
}
