#!/bin/sh
# Gera dist/Claude-Containers-<versão>-x86_64.AppImage (Linux x64). Requer python3, curl.
set -e
cd "$(dirname "$0")"
VER="$(cat VERSION)"
[ -d .venv-build ] || python3 -m venv .venv-build
. .venv-build/bin/activate
pip install -q -r requirements.txt -r requirements-build.txt
pyinstaller --noconfirm --clean claude-containers.spec

AD=build/AppDir
rm -rf "$AD" && mkdir -p "$AD/usr/bin" "$AD/usr/share/icons/hicolor/512x512/apps"
cp -r dist/claude-containers "$AD/usr/bin/"
cp assets/icon.png "$AD/claude-containers.png"
cp assets/icon.png "$AD/.DirIcon"
cp assets/icon.png "$AD/usr/share/icons/hicolor/512x512/apps/claude-containers.png"
cp packaging/claude-containers.desktop "$AD/"
cat > "$AD/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/claude-containers/claude-containers" "$@"
RUN
chmod +x "$AD/AppRun"

TOOL="${APPIMAGETOOL:-build/appimagetool-x86_64.AppImage}"
if [ ! -x "$TOOL" ]; then
  mkdir -p build
  curl -fL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi
OUT="dist/Claude-Containers-$VER-x86_64.AppImage"
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$AD" "$OUT"
echo "OK: $OUT"
