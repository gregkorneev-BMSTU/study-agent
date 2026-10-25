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

let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent(UUID().uuidString)
let realFolder = temporaryRoot.appendingPathComponent("real")
let linkedFolder = temporaryRoot.appendingPathComponent("link")
try FileManager.default.createDirectory(at: realFolder, withIntermediateDirectories: true)
defer { try? FileManager.default.removeItem(at: temporaryRoot) }
try FileManager.default.createSymbolicLink(at: linkedFolder, withDestinationURL: realFolder)
let linkedBookmark = try linkedFolder.bookmarkData(options: [], includingResourceValuesForKeys: nil, relativeTo: nil)
let linkedSavedFolder = SavedFolder(id: UUID(), name: "link", bookmark: linkedBookmark, path: linkedFolder.path)
let canonicalRoot = SavedFolder.canonicalPath(realFolder.path)
precondition(SavedFolder.path(of: linkedSavedFolder) == canonicalRoot)
precondition(SavedFolder.searchRoots([linkedSavedFolder]) == [canonicalRoot])
