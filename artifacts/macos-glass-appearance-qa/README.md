# macOS Liquid Glass settings QA

## API review

Reviewed Apple's [macOS 27 Appearance guide](https://support.apple.com/en-mt/guide/mac-help/mchlp1225/27/mac/27), [macOS 27 release notes](https://support.apple.com/en-us/127257), [WWDC26 Platforms State of the Union](https://developer.apple.com/videos/play/wwdc2026/102/), [Adopting Liquid Glass](https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass), SwiftUI [`Glass`](https://developer.apple.com/documentation/swiftui/glass) and [custom glass effects](https://developer.apple.com/documentation/swiftui/applying-liquid-glass-to-custom-views), AppKit [`NSGlassEffectView`](https://developer.apple.com/documentation/appkit/nsglasseffectview) and its [`tintColor`](https://developer.apple.com/documentation/appkit/nsglasseffectview/tintcolor), [`NSVisualEffectView`](https://developer.apple.com/documentation/appkit/nsvisualeffectview), and SwiftUI's [`accessibilityReduceTransparency`](https://developer.apple.com/documentation/swiftui/environmentvalues/accessibilityreducetransparency) and [`accessibilityShowBorders`](https://developer.apple.com/documentation/swiftui/environmentvalues/accessibilityshowborders).

The reviewed public APIs do **not** expose a numeric value for macOS's Liquid Glass slider, nor a continuous per-app intensity control for native glass. SwiftUI `Glass` exposes `regular`, `clear`, and `identity` variants plus `tint(_:)`; AppKit `NSGlassEffectView` exposes a glass style, tint color, and corner radius. Tint changes color, not the system slider value or a documented transparency coefficient.

The user clarified that Study Agent needs its own independent application transparency slider. This is implemented with the public AppKit `NSWindow.alphaValue`, rather than pretending to control the system Liquid Glass material.

## Implemented behavior

- Settings includes an **App Transparency** slider with outlined/filled endpoint symbols, a visible percentage, and a VoiceOver label/value.
- Slider range is 35–100% window opacity. Changes apply immediately to all current Study Agent windows and persist in `UserDefaults` under `appearance.windowTransparency`.
- The setting is local to the app; it does not read or modify global macOS preferences. It changes the overall window alpha, including text and controls. It is not a per-app native Liquid Glass material-intensity control.
- Native sidebar and toolbar materials continue to follow macOS. The app does not read or modify macOS 27's private/system slider state.

## Compatibility and accessibility

The app deployment target remains macOS 14. `NSWindow.alphaValue` is a public AppKit API available across the supported range. The slider uses the native SwiftUI `Slider`, and the opacity percentage is exposed as its accessibility value. Increase Contrast and appearance styling remain separately controlled by the existing app/system settings.

## QA results

- Host: macOS 27.0.1 (26A434); Xcode 27.1, macOS SDK 27.0.
- Xcode Debug build: succeeded.
- Xcode Release build: succeeded.
- `ruff check .`: passed.
- `.venv/bin/pytest --ignore=tests/test_switch.py`: 31 passed.
- Full `.venv/bin/pytest` aborts during `tests/test_switch.py` QApplication initialization in this host's Cocoa/Qt environment. The remaining test suite passes when that test module is excluded; no source changes were made to hide or alter this environment issue.
- The updated packaged app launches, and its bundle contains the backend. Slider interaction/persistence and low-opacity readability still need a manual visual check in the Settings window.
- A new screenshot was not recorded: the Mac session locked during UI verification. The earlier screenshot showing the system-settings guidance was removed because it no longer matches the revised UI.
- System slider extremes and intermediate positions were not changed or compared because they are global macOS preferences. The app does not read or modify that preference.
- Reduce Transparency, Increase Contrast, and Show Borders were not toggled for visual comparisons. The app-local window alpha is intentionally independent of those settings.
- macOS 14/15/26 were not available for this run; deployment target remains 14.0, but minimum-OS execution was not verified here.
- No continuous effects, timers, or custom blur were added. CPU/GPU profiling and FPS measurements were not performed, so no performance numbers are claimed.

## Limitations

Apple does not document a public API for reading the system slider's numeric position or setting per-app intensity for native Liquid Glass. Study Agent instead offers the explicitly labeled app-local window-opacity control. Because `NSWindow.alphaValue` affects the complete window, text and controls become translucent along with backgrounds; this tradeoff is stated in the settings and should be considered when choosing a low value.
