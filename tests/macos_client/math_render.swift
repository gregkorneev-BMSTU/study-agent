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
        let markdown = #"""
        # Ответ **по материалам**

        **Основная формула:** $x_i^2 + y_j$; *пояснение* и _курсив_.

        $$
        \begin{aligned}
        a_i &= x_i^2 \\

        b_j &= \frac{1}{x_j}
        \end{aligned}
        $$

        - Первый **элемент**
        - Второй с \(z_k\)

        3. Шаг один
        4. Шаг два

        > Цитата с **выделением** и `$literal$`.

        | Формула | Значение |
        | --- | --- |
        | $q_n$ | **полезно** |
        | `a|b` | \(r_s\) |

        ```html
        <script>window.injected=true</script>
        $$not_math$$ **not_bold**
        ```

        <unknown data-value="x">HTML остаётся текстом</unknown>
        <img src="https://example.org/leak" onerror="window.injected=true">
        [ссылка](https://example.org/) ![image](https://example.org/image)
        """#
        _ = try await view.callAsyncJavaScript("window.renderStudyContent(text, false)",
            arguments: ["text": markdown], in: nil, contentWorld: .page)
        let markdownResult = try await view.evaluateJavaScript("""
        ({heading:document.querySelector('h1')?.textContent,
          strong:document.querySelectorAll('strong').length,
          emphasis:document.querySelectorAll('em').length,
          unordered:document.querySelectorAll('ul > li').length,
          ordered:document.querySelectorAll('ol > li').length,
          start:document.querySelector('ol')?.start,
          quote:document.querySelector('blockquote')?.textContent,
          cells:document.querySelectorAll('tbody td').length,
          codeCell:document.querySelector('tbody tr:last-child td:first-child')?.textContent,
          math:document.querySelectorAll('.katex').length,
          latex:[...document.querySelectorAll('annotation')].map(node=>node.textContent),
          errors:document.querySelectorAll('.katex-error').length,
          code:document.querySelector('pre')?.textContent,
          unsafe:document.querySelectorAll('img,script:not([src]),a,unknown').length,
          literal:document.getElementById('content').textContent.includes('<unknown data-value="x">'),
          injected:window.injected===true})
        """) as! [String: Any]
        precondition(markdownResult["heading"] as? String == "Ответ по материалам")
        precondition((markdownResult["strong"] as? Int ?? 0) >= 5)
        precondition(markdownResult["emphasis"] as? Int == 2)
        precondition(markdownResult["unordered"] as? Int == 2)
        precondition(markdownResult["ordered"] as? Int == 2 && markdownResult["start"] as? Int == 3)
        precondition((markdownResult["quote"] as? String)?.contains("$literal$") == true)
        precondition(markdownResult["cells"] as? Int == 4 && markdownResult["codeCell"] as? String == "a|b")
        precondition(markdownResult["math"] as? Int == 5, "Mixed Markdown lost math: \(markdownResult)")
        precondition(markdownResult["errors"] as? Int == 0)
        let annotations = markdownResult["latex"] as? [String] ?? []
        precondition(annotations.contains("x_i^2 + y_j"), "Markdown changed LaTeX underscores")
        precondition(annotations.contains(where: { $0.contains("a_i &= x_i^2") && $0.contains("\n\n") }), "Display math lost blank lines")
        precondition((markdownResult["code"] as? String)?.contains("$$not_math$$ **not_bold**") == true)
        precondition(markdownResult["unsafe"] as? Int == 0 && markdownResult["literal"] as? Bool == true)
        precondition(markdownResult["injected"] as? Bool == false)
        let indentedCode = "    $$literal_math$$ **literal_bold**\n\n\t<script>window.injected=true</script>\n\nParagraph\n    $real_math$"
        _ = try await view.callAsyncJavaScript("window.renderStudyContent(text, false)",
            arguments: ["text": indentedCode], in: nil, contentWorld: .page)
        let indentResult = try await view.evaluateJavaScript("""
        ({code:document.querySelector('pre')?.textContent,
          math:document.querySelectorAll('.katex').length,
          strong:document.querySelectorAll('strong').length,
          scripts:document.querySelectorAll('#content script').length,
          injected:window.injected===true})
        """) as! [String: Any]
        precondition((indentResult["code"] as? String)?.contains("$$literal_math$$ **literal_bold**") == true)
        precondition((indentResult["code"] as? String)?.contains("<script>window.injected=true</script>") == true)
        precondition(indentResult["math"] as? Int == 1, "Indented paragraph continuation must remain prose")
        precondition(indentResult["strong"] as? Int == 0 && indentResult["scripts"] as? Int == 0)
        precondition(indentResult["injected"] as? Bool == false)
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
