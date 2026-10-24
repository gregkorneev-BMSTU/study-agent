# macOS Liquid Glass: API review and QA

## What Apple means by Liquid Glass

Liquid Glass is a dynamic system material, not a window-opacity value. Its rendered appearance responds to the surrounding content, window activity, and accessibility settings; the system adjusts tint, light, and contrast to preserve legibility. Apple recommends keeping it in the navigation and control layer instead of applying it to ordinary content. See [Meet Liquid Glass (WWDC25)](https://developer.apple.com/videos/play/wwdc2025/219/) and [HIG: Materials](https://developer.apple.com/design/human-interface-guidelines/materials).

Apple documents two SwiftUI material variants, `Glass.regular` and `Glass.clear`, plus `Glass.identity` and `tint(_:)`. Clear is a fixed, more transparent variant and needs an appropriate treatment for legibility. `tint(_:)` changes color; it is not a transparency/intensity amount. AppKit `NSGlassEffectView` similarly offers Regular/Clear styles and a tint color. See [SwiftUI `Glass`](https://developer.apple.com/documentation/swiftui/glass), [Clear Glass](https://developer.apple.com/documentation/swiftui/glass/clear), [Applying Liquid Glass to custom views](https://developer.apple.com/documentation/swiftui/applying-liquid-glass-to-custom-views), and [AppKit `NSGlassEffectView`](https://developer.apple.com/documentation/appkit/nsglasseffectview).

macOS 27 provides a system-level slider from ultra-clear to fully tinted in System Settings > Appearance. The reviewed public SwiftUI/AppKit APIs do not expose the slider's numeric position or a continuous per-app intensity control for the native system material. The system slider and `Glass.clear`/`Glass.regular` are distinct mechanisms; the variants are not numeric endpoints of Apple's global scale. See [Apple Support: macOS 27 updates](https://support.apple.com/en-us/127257) and [Change Appearance settings on Mac](https://support.apple.com/en-mt/guide/mac-help/mchlp1225/27/mac/27).

## Study Agent behavior

- The incorrect 35–100% `NSWindow.alphaValue` control has been removed. It changed the opacity of the entire window, including text and controls, and was not Liquid Glass.
- Study Agent's sidebar and toolbar use native SwiftUI/AppKit system surfaces. They continue to follow macOS's appearance and accessibility settings.
- Settings has no Liquid Glass banner, slider, or appearance shortcut. The app leaves the system surfaces alone and does not display a fabricated local intensity value.
- No custom `Glass` surfaces currently exist in Study Agent. Adding a local Regular/Clear selector without an app-owned glass surface would be decorative and misleading, while replacing native sidebar/toolbar to force a custom material would undermine the system behavior. If the app later introduces an appropriate custom navigation/control surface, its fixed `regular`/`clear` variant could be evaluated separately.
- The minimum deployment target remains macOS 14. The new controls use no newer Glass APIs; the app only opens System Settings and describes the macOS 27 slider when available.

## Accessibility and compatibility

System-owned surfaces retain the macOS behavior for Reduce Transparency, Increased Contrast, Reduced Motion, light/dark appearance, and active/inactive windows. Study Agent does not override those preferences. The existing app-level contrast and motion settings remain unchanged.

## QA status

- Reviewed official Apple documentation linked above, including SwiftUI Glass, custom Glass effects, AppKit `NSGlassEffectView`, and the macOS 27 user-facing slider.
- Verified by source inspection that Study Agent's sidebar and toolbar are system controls and that the app has no custom `glassEffect`/`NSGlassEffectView` surface to which a local variant could be meaningfully applied.
- Xcode Debug and Release builds succeeded with Xcode 27.1 / macOS SDK 27.0; the project deployment target remains macOS 14.
- `.venv/bin/ruff check .` passed. `.venv/bin/pytest --ignore=tests/test_switch.py` passed (31 tests). Full `.venv/bin/pytest` aborted in `tests/test_switch.py` during PySide6 `QApplication` fixture initialization on this host; the crash is outside the SwiftUI change.
- The app has not been visually re-captured after this correction because the Mac session locked during UI verification. No new screenshots, Reduce Transparency comparison, VoiceOver run, or performance measurements are claimed here.
- No performance metrics are claimed.
