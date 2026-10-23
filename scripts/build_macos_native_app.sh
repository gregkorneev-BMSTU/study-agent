#!/bin/sh
set -eu

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Build the native macOS app on macOS." >&2
  exit 1
fi

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${PYTHON:-"$ROOT_DIR/.venv/bin/python"}
APP_OUTPUT_DIR=${APP_OUTPUT_DIR:-"$HOME/Applications"}
DERIVED_DATA=${DERIVED_DATA:-"$ROOT_DIR/build/xcode"}
BACKEND_BUILD=${BACKEND_BUILD:-"$ROOT_DIR/build/mac-backend"}
NATIVE_ARCH=$(uname -m)

if [ ! -x "$PYTHON" ]; then
  echo "Python not found at $PYTHON. Create .venv and install '.[packaging]'." >&2
  exit 1
fi
if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
  echo "PyInstaller is missing. Run: $PYTHON -m pip install '.[packaging]'." >&2
  exit 1
fi

cd "$ROOT_DIR"
"$PYTHON" -m PyInstaller \
  --clean \
  --noconfirm \
  --onedir \
  --console \
  --name StudyAgentBackend \
  --paths "$ROOT_DIR/src" \
  --distpath "$BACKEND_BUILD/dist" \
  --workpath "$BACKEND_BUILD/work" \
  --specpath "$BACKEND_BUILD" \
  "$ROOT_DIR/src/study_agent/mac_bridge.py"

xcodebuild \
  -project "$ROOT_DIR/macOS/StudyAgent.xcodeproj" \
  -scheme "Study Agent" \
  -configuration Release \
  -derivedDataPath "$DERIVED_DATA" \
  ARCHS="$NATIVE_ARCH" \
  CODE_SIGNING_ALLOWED=NO \
  build

BUILT_APP="$DERIVED_DATA/Build/Products/Release/Study Agent.app"
APP_PATH="$APP_OUTPUT_DIR/Study Agent.app"
mkdir -p "$APP_OUTPUT_DIR"
rm -rf "$APP_PATH"
ditto "$BUILT_APP" "$APP_PATH"
mkdir -p "$APP_PATH/Contents/Resources/Backend"
ditto "$BACKEND_BUILD/dist/StudyAgentBackend" "$APP_PATH/Contents/Resources/Backend/StudyAgentBackend"
xattr -cr "$APP_PATH"
codesign --force --sign - "$APP_PATH"

echo "Built and ad-hoc signed native macOS app: $APP_PATH"
