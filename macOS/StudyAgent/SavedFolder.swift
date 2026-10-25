import Foundation

struct SavedFolder: Codable, Identifiable, Hashable {
    var id: UUID
    var name: String
    var bookmark: Data
    var path: String? = nil

    static func path(of folder: SavedFolder) -> String? {
        if let path = folder.path { return path }
        var stale = false
        return try? URL(
            resolvingBookmarkData: folder.bookmark,
            options: [],
            relativeTo: nil,
            bookmarkDataIsStale: &stale
        ).path
    }

    static func searchRoots(_ folders: [SavedFolder]) -> [String] {
        folders.compactMap(path(of:))
    }
}
