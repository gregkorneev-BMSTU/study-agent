import SwiftUI
import WebKit

/// Local renderer: document text never becomes HTML and the web view cannot navigate online.
struct MathContentView: View {
    let text: String
    let language: AppLanguage
    @State private var height: CGFloat = 40

    static func containsMath(_ text: String) -> Bool {
        // Do not activate the web renderer for code examples.
        var fence: String?
        var prose: [String] = []
        let markerPattern = try! NSRegularExpression(pattern: #"^ {0,3}(`{3,}|~{3,})"#)
        for line in text.components(separatedBy: .newlines) {
            let value = line as NSString
            if let match = markerPattern.firstMatch(in: line, range: NSRange(location: 0, length: value.length)) {
                let marker = value.substring(with: match.range(at: 1))
                if let current = fence {
                    if current.first == marker.first && marker.count >= current.count { fence = nil }
                } else { fence = marker }
            } else if fence == nil { prose.append(line) }
        }
        let content = maskingInlineCode(prose.joined(separator: "\n"))
        return content.range(of: #"(?s)\$\$.+?\$\$|\\\[.+?\\\]|\\\(.+?\\\)|(?<!\\)\$[^\n$]+?\$"#,
                             options: .regularExpression) != nil
    }

    /// Match code spans by exact backtick-run length, including double backticks
    /// containing literal single backticks. Unmatched/escaped openers stay prose.
    private static func maskingInlineCode(_ text: String) -> String {
        let value = text as NSString
        let runs = try! NSRegularExpression(pattern: "`+")
            .matches(in: text, range: NSRange(location: 0, length: value.length))
        var index = 0
        var cursor = 0
        var prose = ""
        while index < runs.count {
            let opening = runs[index].range
            var position = opening.location - 1
            var backslashes = 0
            while position >= 0 && value.character(at: position) == 92 {
                backslashes += 1
                position -= 1
            }
            if backslashes % 2 == 1 { index += 1; continue }
            guard let closingIndex = runs.indices.dropFirst(index + 1).first(where: {
                runs[$0].range.length == opening.length
            }) else { index += 1; continue }
            let closing = runs[closingIndex].range
            prose += value.substring(with: NSRange(location: cursor, length: opening.location - cursor))
            prose += " "
            cursor = NSMaxRange(closing)
            index = closingIndex + 1
        }
        return prose + value.substring(from: cursor)
    }

    var body: some View {
        if let directory = Bundle.main.resourceURL?.appendingPathComponent("math"),
           FileManager.default.fileExists(atPath: directory.appendingPathComponent("index.html").path) {
            OfflineMathView(text: text, directory: directory, height: $height)
                .frame(height: height)
        } else {
            Text(verbatim: text).textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct OfflineMathView: NSViewRepresentable {
    let text: String
    let directory: URL
    @Binding var height: CGFloat
    @Environment(\.colorScheme) private var colorScheme

    func makeCoordinator() -> Coordinator { Coordinator(height: $height) }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController.add(context.coordinator, name: "mathHeight")
        let view = WKWebView(frame: .zero, configuration: config)
        view.setValue(false, forKey: "drawsBackground")
        view.navigationDelegate = context.coordinator
        context.coordinator.allowedPage = directory.appendingPathComponent("index.html")
        view.loadFileURL(directory.appendingPathComponent("index.html"), allowingReadAccessTo: directory)
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        context.coordinator.text = text
        context.coordinator.dark = colorScheme == .dark
        context.coordinator.render(view)
    }

    static func dismantleNSView(_ view: WKWebView, coordinator: Coordinator) {
        view.configuration.userContentController.removeScriptMessageHandler(forName: "mathHeight")
        view.navigationDelegate = nil
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var text = ""
        var dark = false
        var allowedPage: URL?
        private var loaded = false
        private var renderedText: String?
        private var renderedDark: Bool?
        private var height: Binding<CGFloat>
        init(height: Binding<CGFloat>) { self.height = height }

        func render(_ view: WKWebView) {
            guard loaded, renderedText != text || renderedDark != dark else { return }
            renderedText = text
            renderedDark = dark
            // Structured arguments cross the JS boundary without interpolating document content.
            view.callAsyncJavaScript("window.renderStudyContent(text, dark)",
                arguments: ["text": text, "dark": dark], in: nil, in: .page) { _ in }
        }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            loaded = true
            render(webView)
        }
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            decisionHandler(navigationAction.request.url == allowedPage ? .allow : .cancel)
        }
        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard message.name == "mathHeight", let value = message.body as? NSNumber,
                  value.doubleValue.isFinite else { return }
            let next = max(24, CGFloat(value.doubleValue) + 2)
            if abs(height.wrappedValue - next) > 1 { height.wrappedValue = next }
        }
    }
}
