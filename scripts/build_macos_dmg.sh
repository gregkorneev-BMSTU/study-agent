#!/usr/bin/env bash
set -euo pipefail

# Build a drag-to-Applications disk image. No installer code runs from the image.
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MODE=development
APP_SOURCE=
OUTPUT_DIR=${OUTPUT_DIR:-"$ROOT_DIR/dist"}
SUFFIX=

usage() {
  cat <<'EOF'
Usage: scripts/build_macos_dmg.sh [--mode development|distribution] [--app /path/to/Study\ Agent.app] [--output-dir /path] [--suffix rc.1]

By default, builds the app with scripts/build_macos_native_app.sh first.
--app packages an existing app, useful for reviewing the DMG layout.
Distribution requires DEVELOPER_ID_APPLICATION and NOTARY_PROFILE (a notarytool keychain profile).
EOF
}

while (($#)); do
  case "$1" in
    --mode) MODE=${2:?Missing mode}; shift 2 ;;
    --app) APP_SOURCE=${2:?Missing app path}; shift 2 ;;
    --output-dir) OUTPUT_DIR=${2:?Missing output directory}; shift 2 ;;
    --suffix) SUFFIX=${2:?Missing version suffix}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ $(uname -s) == Darwin ]] || { echo 'A macOS host is required.' >&2; exit 1; }
[[ $(uname -m) == arm64 ]] || { echo 'Only Apple Silicon builds are currently supported.' >&2; exit 1; }
[[ $MODE == development || $MODE == distribution ]] || { echo "Unknown mode: $MODE" >&2; exit 2; }
[[ -z $SUFFIX || $SUFFIX =~ ^[A-Za-z0-9]+([.-][A-Za-z0-9]+)*$ ]] || {
  echo 'Version suffix may only contain letters, numbers, dots, and hyphens.' >&2
  exit 2
}
if [[ $MODE == distribution ]]; then
  : "${DEVELOPER_ID_APPLICATION:?Set DEVELOPER_ID_APPLICATION to a Developer ID Application signing identity.}"
  : "${NOTARY_PROFILE:?Set NOTARY_PROFILE to a configured xcrun notarytool keychain profile.}"
  security find-identity -v -p codesigning | grep -F "$DEVELOPER_ID_APPLICATION" >/dev/null || {
    echo 'Developer ID Application identity was not found in the keychain.' >&2
    exit 1
  }
fi

WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/study-agent-dmg.XXXXXXXX")
MOUNT_POINT="$WORK_DIR/StudyAgentDMG$$"
MOUNTED=0
cleanup() {
  if ((MOUNTED)); then
    hdiutil detach "$MOUNT_POINT" -quiet || hdiutil detach "$MOUNT_POINT" -force -quiet || true
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

if [[ -z $APP_SOURCE ]]; then
  APP_OUTPUT_DIR="$WORK_DIR/app" "$ROOT_DIR/scripts/build_macos_native_app.sh"
  APP_SOURCE="$WORK_DIR/app/Study Agent.app"
fi
[[ -d $APP_SOURCE ]] || { echo "App not found: $APP_SOURCE" >&2; exit 1; }
APP_SOURCE=$(cd "$(dirname "$APP_SOURCE")" && pwd)/$(basename "$APP_SOURCE")
PLIST="$APP_SOURCE/Contents/Info.plist"
MAIN_BINARY="$APP_SOURCE/Contents/MacOS/Study Agent"
BACKEND_BINARY="$APP_SOURCE/Contents/Resources/Backend/StudyAgentBackend/StudyAgentBackend"
[[ -f $PLIST && -x $MAIN_BINARY && -x $BACKEND_BINARY ]] || {
  echo 'The app bundle or bundled Python backend is incomplete.' >&2
  exit 1
}
if ! lipo -archs "$MAIN_BINARY" | grep -qw arm64 || ! lipo -archs "$BACKEND_BINARY" | grep -qw arm64; then
  echo 'Both the Swift app and Python backend must contain arm64 binaries.' >&2
  exit 1
fi
VERSION=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$PLIST")
BUILD=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$PLIST")
[[ $VERSION =~ ^[0-9]+(\.[0-9]+)*$ && $BUILD =~ ^[0-9]+$ ]] || {
  echo 'Invalid Xcode app version/build in Info.plist.' >&2
  exit 1
}

STAGING="$WORK_DIR/staging"
mkdir -p "$STAGING" "$OUTPUT_DIR" "$MOUNT_POINT"
ditto "$APP_SOURCE" "$STAGING/Study Agent.app"
ln -s /Applications "$STAGING/Applications"

if [[ $MODE == distribution ]]; then
  # PyInstaller bundles native extensions outside the Xcode signing phase.
  # Sign each Mach-O first, then framework containers, then the outer app.
  while IFS= read -r -d '' item; do
    if file -b "$item" | grep -q 'Mach-O'; then
      codesign --force --timestamp --options runtime --sign "$DEVELOPER_ID_APPLICATION" "$item"
    fi
  done < <(find "$STAGING/Study Agent.app" -type f -print0)
  while IFS= read -r -d '' framework; do
    codesign --force --timestamp --options runtime --sign "$DEVELOPER_ID_APPLICATION" "$framework"
  done < <(find "$STAGING/Study Agent.app" -depth -type d -name '*.framework' -print0)
  codesign --force --timestamp --options runtime --sign "$DEVELOPER_ID_APPLICATION" "$STAGING/Study Agent.app"
  codesign --verify --deep --strict --verbose=2 "$STAGING/Study Agent.app"
  ditto -c -k --keepParent "$STAGING/Study Agent.app" "$WORK_DIR/signed-app.zip"
  xcrun notarytool submit "$WORK_DIR/signed-app.zip" --keychain-profile "$NOTARY_PROFILE" \
    --wait --output-format json > "$WORK_DIR/app-notary.json"
  /usr/bin/python3 -c 'import json,sys; result=json.load(open(sys.argv[1])); print("App notarization:", result.get("status")); sys.exit(result.get("status") != "Accepted")' \
    "$WORK_DIR/app-notary.json"
  xcrun stapler staple "$STAGING/Study Agent.app"
  xcrun stapler validate "$STAGING/Study Agent.app"
fi

IMAGE="$OUTPUT_DIR/StudyAgent-v${VERSION}${SUFFIX:+-$SUFFIX}-macos-arm64.dmg"
[[ ! -e $IMAGE ]] || { echo "Output already exists: $IMAGE" >&2; exit 1; }
READ_WRITE_IMAGE="$WORK_DIR/layout.dmg"
VOLUME_NAME="Study Agent $VERSION${SUFFIX:+ $SUFFIX}"
LAYOUT_STAGE="$WORK_DIR/layout-stage"
mkdir -p "$LAYOUT_STAGE/Study Agent.app"
ln -s /Applications "$LAYOUT_STAGE/Applications"
hdiutil create -quiet -fs HFS+ -format UDRW -volname "$VOLUME_NAME" \
  -srcfolder "$LAYOUT_STAGE" "$READ_WRITE_IMAGE"
hdiutil attach -quiet -readwrite -noautoopen -mountpoint "$MOUNT_POINT" "$READ_WRITE_IMAGE"
MOUNTED=1

# Finder writes these view options into .DS_Store. The default Finder background
# follows the system's light/dark appearance, unlike a baked-in PNG backdrop.
if ! osascript - "$MOUNT_POINT" <<'APPLESCRIPT'
on run argv
  set volumePath to item 1 of argv
  with timeout of 60 seconds
    tell application "Finder"
      set volumeFolder to (POSIX file volumePath) as alias
      open volumeFolder
      set installerWindow to container window of volumeFolder
      set current view of installerWindow to icon view
      set toolbar visible of installerWindow to false
      set statusbar visible of installerWindow to false
      set bounds of installerWindow to {180, 120, 840, 500}
      set arrangement of icon view options of installerWindow to not arranged
      set position of item "Study Agent.app" of volumeFolder to {170, 190}
      set position of item "Applications" of volumeFolder to {490, 190}
      update volumeFolder without registering applications
      set icon size of icon view options of installerWindow to 128
      delay 2
      close installerWindow
      delay 1
    end tell
  end timeout
end run
APPLESCRIPT
then
  echo 'Finder could not save the DMG layout. Allow Terminal/Codex to control Finder in macOS Privacy & Security → Automation, then retry.' >&2
  exit 1
fi
sync
[[ -s "$MOUNT_POINT/.DS_Store" ]] || { echo 'Finder did not save the DMG view settings.' >&2; exit 1; }
cp "$MOUNT_POINT/.DS_Store" "$STAGING/.DS_Store"
hdiutil detach "$MOUNT_POINT" -quiet
MOUNTED=0
# Finder sometimes writes its cached 48 pt icon preference while closing the
# temporary volume. The icon-view plist contains one fixed-width float for the
# icon size; change only that value and verify the plist before packaging.
/usr/bin/python3 - "$STAGING/.DS_Store" <<'PY'
import pathlib
import plistlib
import struct
import sys

path = pathlib.Path(sys.argv[1])
data = bytearray(path.read_bytes())
record = data.index(b"icvpblob")
length = struct.unpack(">I", data[record + 8:record + 12])[0]
start = record + 12
payload = bytes(data[start:start + length])
old_size = plistlib.loads(payload)["iconSize"]
if old_size != 128.0:
    marker = b"\x23" + struct.pack(">d", float(old_size))
    if payload.count(marker) != 1:
        raise SystemExit("Cannot safely set Finder icon size in .DS_Store")
    index = payload.index(marker) + 1
    data[start + index:start + index + 8] = struct.pack(">d", 128.0)
    if plistlib.loads(bytes(data[start:start + length]))["iconSize"] != 128.0:
        raise SystemExit("Finder icon size verification failed")
    path.write_bytes(data)
PY
hdiutil create -quiet -fs HFS+ -format UDZO -imagekey zlib-level=9 \
  -volname "$VOLUME_NAME" -srcfolder "$STAGING" "$IMAGE"

if [[ $MODE == distribution ]]; then
  xcrun notarytool submit "$IMAGE" --keychain-profile "$NOTARY_PROFILE" \
    --wait --output-format json > "$WORK_DIR/dmg-notary.json"
  /usr/bin/python3 -c 'import json,sys; result=json.load(open(sys.argv[1])); print("DMG notarization:", result.get("status")); sys.exit(result.get("status") != "Accepted")' \
    "$WORK_DIR/dmg-notary.json"
  xcrun stapler staple "$IMAGE"
  xcrun stapler validate "$IMAGE"
fi

shasum -a 256 "$IMAGE"
echo "Created $MODE DMG for Study Agent $VERSION (build $BUILD): $IMAGE"
