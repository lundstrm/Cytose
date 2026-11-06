#!/bin/sh
# Run from the repository root in an environment with the Python dependencies and PyInstaller.
set -eu
# Keep all intermediate, unoptimized artifacts outside the project directory.
staging=$(mktemp -d "${TMPDIR:-/tmp}/cytose-package.XXXXXX")
mkdir -p dist/macos
python -m PyInstaller --noconfirm --clean --windowed \
  --name Cytose --icon "$PWD/Assets/Cytose.icns" \
  --add-data "$PWD/python/cytose/fonts:cytose/fonts" \
  --exclude-module PySide6.QtNetwork --exclude-module ssl --exclude-module _ssl \
  --osx-bundle-identifier org.cytose.python \
  --distpath "$staging/raw" --workpath "$staging/work" \
  --specpath "$staging" --paths "$PWD/python" "$PWD/python/launch.py"
# Stage outside cloud-synced folders, which may attach Finder attributes that invalidate signatures.
ditto --noextattr --norsrc "$staging/raw/Cytose.app" "$staging/Cytose.app"
python python/trim_macos_bundle.py "$staging/Cytose.app"
python python/prepare_licenses.py "$staging/Cytose.app/Contents/Resources/Legal" "$staging/Cytose.app"
plist="$staging/Cytose.app/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string 0.1.0 "$plist"
plutil -insert CFBundleVersion -string 0.1.0 "$plist"
# The build environment's Python 3.13 requires macOS 15 or later.
plutil -insert LSMinimumSystemVersion -string 15.0 "$plist"
xattr -cr "$staging/Cytose.app"
codesign --force --deep --sign - "$staging/Cytose.app"
codesign --verify --deep --strict "$staging/Cytose.app"
QT_QPA_PLATFORM=offscreen "$staging/Cytose.app/Contents/MacOS/Cytose" --bundle-smoke-test
if [ -e dist/macos/Cytose.app ]; then
  mv dist/macos/Cytose.app "$staging/previous.app"
fi
ditto --noextattr --norsrc "$staging/Cytose.app" dist/macos/Cytose.app
ditto -c -k --keepParent "$staging/Cytose.app" dist/macos/Cytose-macOS-AppleSilicon.zip
