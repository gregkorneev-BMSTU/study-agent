import SwiftUI
import WebKit

/// Local renderer: document text never becomes HTML and the web view cannot navigate online.
struct MathContentView: View {
    let text: String
    let language: AppLanguage
    var resourceDirectory: URL? = nil
    @State private var height: CGFloat = 40
    @State private var rendered = false
    @State private var renderFailed = false

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
        VStack(alignment: .leading, spacing: 0) {
            // Keep the document visible while WebKit starts, and permanently fall
            // back to selectable text if loading or rendering fails.
            if !rendered || renderFailed {
                Text(verbatim: text).textSelection(.enabled)
                    .accessibilityIdentifier(renderFailed ? "math-render-fallback" : "math-loading-original")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            if !renderFailed,
               let directory = resourceDirectory ?? Bundle.main.resourceURL?.appendingPathComponent("math"),
               FileManager.default.fileExists(atPath: directory.appendingPathComponent("index.html").path) {
                OfflineMathView(text: text, directory: directory, height: $height,
                                rendered: $rendered, failed: $renderFailed)
                    .frame(maxWidth: .infinity)
                    .frame(height: rendered ? height : 1)
                    .opacity(rendered ? 1 : 0)
                    .accessibilityHidden(!rendered)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct OfflineMathView: NSViewRepresentable {
    let text: String
    let directory: URL
    @Binding var height: CGFloat
    @Binding var rendered: Bool
    @Binding var failed: Bool
    @Environment(\.colorScheme) private var colorScheme

    func makeCoordinator() -> Coordinator {
        Coordinator(height: $height, rendered: $rendered, failed: $failed)
    }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController.add(context.coordinator, name: "mathHeight")
        let view = EmbeddedDocumentWebView(frame: .zero, configuration: config)
        view.setValue(false, forKey: "drawsBackground")
        view.navigationDelegate = context.coordinator
        context.coordinator.text = text
        context.coordinator.dark = colorScheme == .dark
        context.coordinator.allowedPage = directory.appendingPathComponent("index.html")
        view.loadFileURL(directory.appendingPathComponent("index.html"), allowingReadAccessTo: directory)
        context.coordinator.startLoadTimeout()
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        context.coordinator.text = text
        context.coordinator.dark = colorScheme == .dark
        context.coordinator.render(view)
    }

    static func dismantleNSView(_ view: WKWebView, coordinator: Coordinator) {
        coordinator.cancel()
        view.configuration.userContentController.removeScriptMessageHandler(forName: "mathHeight")
        view.navigationDelegate = nil
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var text = ""
        var dark = false
        var allowedPage: URL?
        private var loaded = false
        private var cancelled = false
        private var renderedText: String?
        private var renderedDark: Bool?
        private var generation = 0
        private var loadTimeout: Task<Void, Never>?
        private var height: Binding<CGFloat>
        private var rendered: Binding<Bool>
        private var failed: Binding<Bool>
        init(height: Binding<CGFloat>, rendered: Binding<Bool>, failed: Binding<Bool>) {
            self.height = height
            self.rendered = rendered
            self.failed = failed
        }

        func startLoadTimeout() {
            loadTimeout = Task { @MainActor [weak self] in
                try? await Task.sleep(nanoseconds: 8_000_000_000)
                guard !Task.isCancelled, let self, !self.cancelled,
                      !self.rendered.wrappedValue else { return }
                self.fail()
            }
        }
        func cancel() { cancelled = true; loadTimeout?.cancel() }
        private func fail() {
            guard !cancelled else { return }
            loadTimeout?.cancel()
            failed.wrappedValue = true
            rendered.wrappedValue = false
        }
        func render(_ view: WKWebView) {
            guard loaded, !cancelled, renderedText != text || renderedDark != dark else { return }
            let currentText = text
            let currentDark = dark
            renderedText = currentText
            renderedDark = currentDark
            generation += 1
            let currentGeneration = generation
            // Structured arguments cross the JS boundary without interpolating source text.
            // Verify both the renderer and its output; a JS exception cannot leave a blank card.
            view.callAsyncJavaScript("""
                if (typeof window.renderStudyContent !== 'function') throw new Error('Renderer unavailable');
                window.renderStudyContent(text, dark);
                const root = document.getElementById('content');
                if (!root || (text.trim() && !root.textContent.trim())) throw new Error('Empty renderer output');
                return Math.ceil(root.getBoundingClientRect().height);
                """, arguments: ["text": currentText, "dark": currentDark], in: nil, in: .page) { [weak self] result in
                    guard let self, !self.cancelled, self.generation == currentGeneration else { return }
                    guard case .success(let value) = result, let measured = value as? NSNumber,
                          measured.doubleValue.isFinite else { self.fail(); return }
                    self.height.wrappedValue = max(24, CGFloat(measured.doubleValue) + 2)
                    self.rendered.wrappedValue = true
                    self.loadTimeout?.cancel()
                }
        }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            loaded = true
            render(webView)
        }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { fail() }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { fail() }
        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { fail() }
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            let requested = navigationAction.request.url
            let isEntryPage = requested?.isFileURL == true
                && requested?.standardizedFileURL.resolvingSymlinksInPath().path
                    == allowedPage?.standardizedFileURL.resolvingSymlinksInPath().path
            decisionHandler(isEntryPage ? .allow : .cancel)
        }
        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard !cancelled, message.name == "mathHeight", let value = message.body as? NSNumber,
                  value.doubleValue.isFinite else { return }
            let next = max(24, CGFloat(value.doubleValue) + 2)
            if abs(height.wrappedValue - next) > 1 { height.wrappedValue = next }
        }
    }
}

/// The embedded document grows to its content height, so vertical wheel events
/// belong to the surrounding results scroll view. WebKit otherwise consumes
/// them even though its own document has no vertical scrolling range.
private final class EmbeddedDocumentWebView: WKWebView {
    private var forwardingVerticalGesture = false

    override func scrollWheel(with event: NSEvent) {
        let vertical = abs(event.scrollingDeltaY) > abs(event.scrollingDeltaX)
            || (event.scrollingDeltaX == 0 && event.scrollingDeltaY == 0 && forwardingVerticalGesture)
        if event.scrollingDeltaX != 0 || event.scrollingDeltaY != 0 {
            forwardingVerticalGesture = vertical
        }
        defer {
            if event.phase.contains(.cancelled) || event.momentumPhase.contains(.ended) {
                forwardingVerticalGesture = false
            }
        }
        if vertical && !event.modifierFlags.contains(.shift) {
            var ancestor = superview
            while let current = ancestor {
                if let outer = current as? NSScrollView {
                    outer.scrollWheel(with: event)
                    return
                }
                ancestor = current.superview
            }
        }
        // Horizontal wheel events remain in WebKit for overflowing formulas and
        // tables. Mouse selection and the accessible MathML tree are unchanged.
        super.scrollWheel(with: event)
    }
}
