#!/usr/bin/env bash
# Packs a built hanami binary into hanami-x86_64.AppImage.
#
#   packaging/linux/appimage.sh target/release/hanami [out.AppImage]
#
# Uses appimagetool from github.com/AppImage/appimagetool (the continuous
# build is the current release line; it fetches the static type2 runtime
# from github.com/AppImage/type2-runtime). Set APPIMAGETOOL to use a copy
# you already have. Needs patchelf, and libxkbcommon-x11-0 installed (its
# libraries are copied in).
set -euo pipefail

binary=${1:?path to the hanami binary}
out=${2:-hanami-x86_64.AppImage}
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

appdir="$work/Hanami.AppDir"
mkdir -p "$appdir/usr/bin" "$appdir/usr/share/applications" "$appdir/usr/share/icons/hicolor/scalable/apps" "$appdir/usr/share/doc/hanami"
install -m 755 "$binary" "$appdir/usr/bin/hanami"
install -m 644 "$here/hanami.desktop" "$appdir/usr/share/applications/hanami.desktop"
install -m 644 "$root/assets/hanami-icon.svg" "$appdir/usr/share/icons/hicolor/scalable/apps/hanami.svg"
install -m 644 "$root/README.md" "$root/GUIDE.md" "$root/LICENSE" "$appdir/usr/share/doc/hanami/"
# winit opens the xkbcommon libraries only once it runs, and the X11 one is
# missing on many systems. The copies go in usr/lib, which hanami (and the
# copies themselves) look in first. A RUNPATH, not LD_LIBRARY_PATH: that
# would pass down to every game Hanami starts.
mkdir -p "$appdir/usr/lib"
for lib in libxkbcommon.so.0 libxkbcommon-x11.so.0 libxcb-xkb.so.1; do
  path=$(ldconfig -p | awk -v lib="$lib" '$1 == lib && /x86-64/ { print $NF; exit }')
  [ -n "$path" ] || { echo "$lib not found; install libxkbcommon-x11-0" >&2; exit 1; }
  cp -L "$path" "$appdir/usr/lib/$lib"
  chmod 644 "$appdir/usr/lib/$lib"
  patchelf --set-rpath '$ORIGIN' "$appdir/usr/lib/$lib"
done
patchelf --set-rpath '$ORIGIN/../lib' "$appdir/usr/bin/hanami"
ln -s usr/bin/hanami "$appdir/AppRun"
ln -s usr/share/applications/hanami.desktop "$appdir/hanami.desktop"
ln -s usr/share/icons/hicolor/scalable/apps/hanami.svg "$appdir/hanami.svg"
ln -s hanami.svg "$appdir/.DirIcon"

tool=${APPIMAGETOOL:-"$work/appimagetool"}
if [ ! -x "$tool" ]; then
  curl -sSfL -o "$tool" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$tool"
fi
# --appimage-extract-and-run: the tool itself is an AppImage and the build
# machine may have no FUSE.
ARCH=x86_64 "$tool" --appimage-extract-and-run --no-appstream "$appdir" "$out"
