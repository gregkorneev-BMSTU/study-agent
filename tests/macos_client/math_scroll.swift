import AppKit
import SwiftUI
import WebKit

/// Native event routing in the actual SwiftUI/WKWebView hierarchy, using only
/// synthetic material. Run separately from math_render.swift.
@main
struct MathScrollTest {
    @MainActor static func main() async throws {
        _ = NSApplication.shared
        let directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("assets/math")
        let text = "# Source\n\nSelectable prose.\n\n$$" + Array(repeating: "x_i^2", count: 80).joined(separator: "+") + "$$"
        let host = NSHostingView(rootView: ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(0..<12) { _ in
                    MathContentView(text: text, language: .english, resourceDirectory: directory).padding(10)
                }
            }
        }.frame(width: 600, height: 360))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 360),
            styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host; window.orderFront(nil)
        defer { window.orderOut(nil) }
        func descendants<T: NSView>(_ root: NSView, _: T.Type) -> [T] {
            (root as? T).map { [$0] } ?? root.subviews.flatMap { descendants($0, T.self) }
        }
        var webViews: [WKWebView] = []
        for _ in 0..<200 {
            host.layoutSubtreeIfNeeded()
            webViews = descendants(host, WKWebView.self)
            if webViews.count == 12, webViews.allSatisfy({ $0.frame.height > 40 }) { break }
            try await Task.sleep(nanoseconds: 50_000_000)
        }
        precondition(webViews.count == 12)
        let web = webViews[0]
        var ancestor: NSView? = web.superview
        while ancestor != nil && !(ancestor is NSScrollView) { ancestor = ancestor?.superview }
        let outer = ancestor as! NSScrollView
        precondition(outer.documentView!.bounds.height > outer.contentView.bounds.height * 2)
        try await Task.sleep(nanoseconds: 700_000_000) // Fonts/height observer settle.
        let stableHeights = webViews.map { $0.frame.height }
        let stableDocumentHeight = outer.documentView!.bounds.height

        func sendWheel(_ view: WKWebView, y: CGFloat, deltaY: Int32, deltaX: Int32 = 0) {
            let local = NSPoint(x: 100, y: y)
            let receiver = view.hitTest(view.convert(local, to: view.superview))!
            let cg = CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 2,
                wheel1: deltaY, wheel2: deltaX, wheel3: 0)!
            cg.location = window.convertPoint(toScreen: view.convert(local, to: nil))
            receiver.scrollWheel(with: NSEvent(cgEvent: cg)!)
        }
        let start = outer.contentView.bounds.origin.y
        sendWheel(web, y: 20, deltaY: -60) // Prose portion.
        try await Task.sleep(nanoseconds: 100_000_000)
        let downOverProse = outer.contentView.bounds.origin.y
        precondition(downOverProse > start + 20, "Vertical wheel over rendered prose was trapped")
        sendWheel(web, y: web.bounds.height - 15, deltaY: -60) // Formula portion.
        try await Task.sleep(nanoseconds: 100_000_000)
        let downOverMath = outer.contentView.bounds.origin.y
        precondition(downOverMath > downOverProse + 20, "Vertical wheel over rendered math was trapped")
        sendWheel(web, y: web.bounds.height - 15, deltaY: 60)
        try await Task.sleep(nanoseconds: 100_000_000)
        let upOverMath = outer.contentView.bounds.origin.y
        precondition(upOverMath < downOverMath - 20, "Upward wheel over math was trapped")
        sendWheel(web, y: 20, deltaY: 60)
        try await Task.sleep(nanoseconds: 100_000_000)
        precondition(outer.contentView.bounds.origin.y < upOverMath - 20, "Upward wheel over prose was trapped")

        let beforeHorizontal = outer.contentView.bounds.origin.y
        sendWheel(web, y: web.bounds.height - 15, deltaY: 0, deltaX: -100)
        try await Task.sleep(nanoseconds: 100_000_000)
        precondition(abs(outer.contentView.bounds.origin.y - beforeHorizontal) < 1,
            "Horizontal wheel must remain in WebKit")
        let dom = try await web.evaluateJavaScript("""
        (() => {
          const formula = document.querySelector('.katex-display');
          const style = getComputedStyle(formula);
          formula.scrollLeft = 100;
          const range = document.createRange();
          range.selectNodeContents(document.querySelector('p'));
          const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
          return {overflow:style.overflowX, scrollable:formula.scrollWidth>formula.clientWidth,
            horizontal:formula.scrollLeft, selected:selection.toString(),
            mathml:document.querySelectorAll('math').length};
        })()
        """) as! [String: Any]
        precondition(dom["scrollable"] as? Bool == true && dom["overflow"] as? String == "auto")
        precondition((dom["horizontal"] as? Double ?? 0) > 0, "Formula horizontal overflow was removed")
        precondition(dom["selected"] as? String == "Selectable prose.")
        precondition(dom["mathml"] as? Int == 1)
        // Native routing must not trigger repeated document re-renders/heights.
        try await Task.sleep(nanoseconds: 500_000_000)
        host.layoutSubtreeIfNeeded()
        precondition(zip(webViews.map { $0.frame.height }, stableHeights).allSatisfy { abs($0 - $1) < 2 })
        precondition(abs(outer.documentView!.bounds.height - stableDocumentHeight) < 2,
            "Wheel events triggered a height/layout feedback loop")
        print("Native wheel over prose/math scrolls results both ways; horizontal overflow, selection, MathML and 12-card heights remain stable")
    }
}
