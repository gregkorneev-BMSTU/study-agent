#!/bin/sh
set -eu

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Build the macOS app on macOS." >&2
  exit 1
fi

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${PYTHON:-"$ROOT_DIR/.venv/bin/python"}
APP_OUTPUT_DIR=${APP_OUTPUT_DIR:-"$HOME/Applications"}

if [ ! -x "$PYTHON" ]; then
  echo "Python not found at $PYTHON. Create .venv and install '.[packaging]'." >&2
  exit 1
fi

if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
  echo "PyInstaller is missing. Run: $PYTHON -m pip install '.[packaging]'" >&2
  exit 1
fi

cd "$ROOT_DIR"
mkdir -p "$APP_OUTPUT_DIR"
"$PYTHON" -m PyInstaller \
  --clean \
  --noconfirm \
  --windowed \
  --name "Study Agent" \
  --osx-bundle-identifier com.gregkorneev.studyagent \
  --icon "$ROOT_DIR/assets/StudyAgent_Apple_Icon_Kit/macOS/StudyAgent.icns" \
  --add-data "$ROOT_DIR/assets/StudyAgent_Apple_Icon_Kit/Master/AppIcon_1024.png:study_agent/assets" \
  --add-data "$ROOT_DIR/src/study_agent/assets/sf_symbols:study_agent/assets/sf_symbols" \
  --paths "$ROOT_DIR/src" \
  --distpath "$APP_OUTPUT_DIR" \
  --workpath "$ROOT_DIR/build/pyinstaller" \
  --specpath "$ROOT_DIR/build/pyinstaller" \
  "$ROOT_DIR/src/study_agent/__main__.py"

APP_PATH="$APP_OUTPUT_DIR/Study Agent.app"
xattr -cr "$APP_PATH"
find "$APP_PATH/Contents/Frameworks" -type d -name '*.framework' \
  -exec sh -c 'for path do xattr -d com.apple.FinderInfo "$path" 2>/dev/null || true; done' sh {} +
codesign --force --deep --sign - "$APP_PATH"

echo "Built and ad-hoc signed: $APP_PATH"
