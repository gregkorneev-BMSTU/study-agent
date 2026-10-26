import AppKit
import WebKit

/// Synthetic offline smoke test. No user documents, running app or index are accessed.
@main
struct MathRenderTest {
    @MainActor static func main() async throws {
        _ = NSApplication.shared
        precondition(MathContentView.containsMath(#"$$\int \sqrt{x}\,dx = \frac{2}{3}x^{3/2}+C$$"#))
        precondition(MathContentView.containsMath(#"Inline \(x^2\) and $x$"#))
        precondition(!MathContentView.containsMath("```tex\n$$x$$\n```\nplain"))
        precondition(!MathContentView.containsMath("Запишите `$x^2$` буквально."))
        precondition(!MathContentView.containsMath(#"Запишите ``$x^2$ и `backtick` и \(y\)`` буквально."#))
        precondition(MathContentView.containsMath(#"Код `$x$`, формула \(y\)."#))
        precondition(MathContentView.containsMath(#"Незакрытый ` и $x$"#))
        precondition(!MathContentView.containsMath("````tex\n$$x$$\n```\n$$y$$\n````"))
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("assets/math")
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        let delegate = RendererDelegate()
        config.userContentController.add(delegate, name: "mathHeight")
        let view = WKWebView(frame: CGRect(x: 0, y: 0, width: 540, height: 900), configuration: config)
        view.navigationDelegate = delegate
        view.loadFileURL(directory.appendingPathComponent("index.html"), allowingReadAccessTo: directory)
        try await delegate.waitUntilLoaded()
        let text = #"$$\int \sqrt{x}\,dx = \frac{2}{3}x^{3/2}+C$$"#
            + "\n<img src='https://example.org/leak' onerror='window.injected=true'>\n"
            + "```tex\n$$code$$\n```\n"
            + #"\(\href{https://example.org}{unsafe}\)"#
        _ = try await view.callAsyncJavaScript("window.renderStudyContent(text, false)",
            arguments: ["text": text], in: nil, contentWorld: .page)
        let result = try await view.evaluateJavaScript("""
        ({math:document.querySelectorAll('.katex').length,
          mathml:document.querySelectorAll('math').length,
          images:document.querySelectorAll('img').length,
          links:document.querySelectorAll('a').length,
          injected:window.injected===true,
          code:document.querySelector('pre').textContent,
          height:document.getElementById('content').getBoundingClientRect().height})
        """) as! [String: Any]
        precondition(result["math"] as? Int == 2, "Math renderer did not initialize: \(result)")
        precondition(result["mathml"] as? Int == 2)
        precondition(result["images"] as? Int == 0)
        precondition(result["links"] as? Int == 0)
        precondition(result["injected"] as? Bool == false)
        precondition((result["code"] as? String)?.contains("$$code$$") == true)
        precondition((result["height"] as? Double ?? 0) > 40)
        let inlineCode = #"Запишите `$x^2$` буквально. ``$y^2$ и `backtick` и \(z\)`` <img src=x onerror='window.injected=true'>"#
        _ = try await view.callAsyncJavaScript("window.renderStudyContent(text, false)",
            arguments: ["text": inlineCode], in: nil, contentWorld: .page)
        let codeResult = try await view.evaluateJavaScript("""
        ({math:document.querySelectorAll('.katex').length,
          code:[...document.querySelectorAll('code')].map(node=>node.textContent),
          images:document.querySelectorAll('img').length,
          injected:window.injected===true})
        """) as! [String: Any]
        precondition(codeResult["math"] as? Int == 0, "Inline code must remain literal")
        precondition(codeResult["code"] as? [String] == ["$x^2$", #"$y^2$ и `backtick` и \(z\)"#])
        precondition(codeResult["images"] as? Int == 0 && codeResult["injected"] as? Bool == false)
        _ = try await view.callAsyncJavaScript("window.renderStudyContent(text, false)",
            arguments: ["text": #"Код `$x$`, формула \(y\)."#], in: nil, contentWorld: .page)
        let mixedMath = try await view.evaluateJavaScript("document.querySelectorAll('.katex').length") as? Int
        precondition(mixedMath == 1, "Math outside inline code must still render")
        let networkBlocked = try await view.callAsyncJavaScript(
            "try { await fetch('https://example.org/blocked'); return false; } catch (_) { return true; }",
            arguments: [:], in: nil, contentWorld: .page) as? Bool
        precondition(networkBlocked == true, "CSP must block network requests")
        _ = try await view.callAsyncJavaScript("window.renderStudyContent(text, true)",
            arguments: ["text": #"$$\def\a{\a}\a$$"#], in: nil, contentWorld: .page)
        let bounded = try await view.evaluateJavaScript("document.querySelectorAll('.katex-error').length") as? Int
        precondition(bounded == 1, "Recursive macros must stop at the expansion limit")
        let scheme = try await view.evaluateJavaScript("document.documentElement.style.colorScheme") as? String
        precondition(scheme == "dark")
        print("Offline math rendering, accessibility, macro limits and untrusted-content checks passed")
    }
}

@MainActor
final class RendererDelegate: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {}
    private var completion: CheckedContinuation<Void, Error>?
    func waitUntilLoaded() async throws {
        try await withCheckedThrowingContinuation { completion = $0 }
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        completion?.resume(); completion = nil
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        completion?.resume(throwing: error); completion = nil
    }
}
