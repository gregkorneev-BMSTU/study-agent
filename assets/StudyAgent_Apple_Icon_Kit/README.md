# Study Agent — Apple icon kit

## Files
- `Master/AppIcon_1024.png` — 1024×1024 PNG with alpha-masked rounded icon, preferred for classic macOS assets.
- `Master/AppIcon_1024_flat_white.png` — same existing approved graphic with original white corners, for reference (not ideal for Dock).
- `macOS/StudyAgent.icns` — legacy macOS app icon, contains all standard sizes incl. 16 px.
- `macOS/AppIcon.iconset` — 10 Apple iconset PNG files (16,32,128,256,512 @1x/@2x).
- `macOS/Assets.xcassets` — drag this asset catalog into Xcode or copy the .appiconset and .imageset into your existing catalog.
- `MenuBar/MenuBarIcon.svg` — clean monochrome vector for NSStatusItem.
- `MenuBar/MenuBarIconTemplate_*.png` — menu bar black+transparent raster sizes.
- `IconComposer_Layers/01...04*.svg` — optional vector reconstruction for importing as separate layers into Apple's Icon Composer; see BACKGROUND_CONFIGURATION.txt.
- `PREVIEW.png` — rendering comparison at small sizes.

## Rights and license

This repository's MIT License applies to the Study Agent source code; it does not automatically license these graphics. The kit does not currently record the creator/source and license of every included artwork layer. Until provenance is confirmed and a specific asset license is added, do not assume these files may be redistributed or modified under MIT. See the repository's [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).

## Sizes included (macOS)
16/32/128/256/512 points, 1x and 2x (respectively 16,32,32,64,128,256,256,512,512,1024 pixels). The .icns also includes 16,32,64,128,256,512,1024 PNG-based entries.

## Menu bar
Default 18 pt artwork supplied as MenuBarIconTemplate.png (18x18 at 1x, 36x36 at 2x), with alternatives in MenuBar folder for 16/20/22/24 pt and retina versions. Unlike the full-color app icon, this uses black pixels and transparent background. To use in AppKit:

```swift
let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
if let image = NSImage(named: "MenuBarIcon") {
    image.isTemplate = true
    image.size = NSSize(width: 18, height: 18)
    item.button?.image = image
}
```

If loading directly from file rather than asset catalog, use an NSImage whose `isTemplate` is true. Do not put the full-color app icon in the menu bar.

## Liquid Glass / Icon Composer
Apple's current 1024×1024 macOS design is layered. A native `.icon` file must be produced using Apple's Icon Composer, which isn't available in this Linux generation environment. This package deliberately does NOT provide a misleading or invalid `.icon` file. The provided SVG layers are a clean vector adaptation suitable for importing into Icon Composer; the exact source artwork is also included as PNG.

Official references:
- https://developer.apple.com/design/human-interface-guidelines/app-icons
- https://developer.apple.com/documentation/Xcode/creating-your-app-icon-using-icon-composer
- https://developer.apple.com/library/archive/documentation/Xcode/Reference/xcode_ref-Asset_Catalog_Format/IconSetType.html
- https://developer.apple.com/documentation/appkit/nsimage/istemplate

## Using in non-Xcode desktop apps
Use `macOS/StudyAgent.icns` as the macOS bundle icon (`CFBundleIconFile` / builder option). The menu bar icon should remain a separate template asset. Windows `.ico` is a different format and is not part of Apple's requirements.
