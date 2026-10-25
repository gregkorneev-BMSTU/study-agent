import Foundation

let offline = SavedFolder(
    id: UUID(), name: "offline", bookmark: Data([0, 1, 2]), path: "/Volumes/offline/notes"
)
precondition(SavedFolder.searchRoots([offline]) == ["/Volumes/offline/notes"])
let unreadable = SavedFolder(id: UUID(), name: "legacy offline", bookmark: Data([0, 1, 2]))
precondition(SavedFolder.searchRoots([unreadable, offline]) == ["/Volumes/offline/notes"])

let encoded = try JSONEncoder().encode([offline])
let restored = try JSONDecoder().decode([SavedFolder].self, from: encoded)
precondition(SavedFolder.searchRoots(restored) == ["/Volumes/offline/notes"])

let folderURL = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
let bookmark = try folderURL.bookmarkData(options: [], includingResourceValuesForKeys: nil, relativeTo: nil)
let legacy = SavedFolder(id: UUID(), name: "legacy", bookmark: bookmark)
var legacyJSON = try JSONSerialization.jsonObject(with: JSONEncoder().encode(legacy)) as! [String: Any]
legacyJSON.removeValue(forKey: "path")
let legacyData = try JSONSerialization.data(withJSONObject: legacyJSON)
let decodedLegacy = try JSONDecoder().decode(SavedFolder.self, from: legacyData)
let legacyRoots = SavedFolder.searchRoots([decodedLegacy])
precondition(legacyRoots.count == 1 && FileManager.default.fileExists(atPath: legacyRoots[0]))
