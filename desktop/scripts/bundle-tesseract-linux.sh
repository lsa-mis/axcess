#!/usr/bin/env bash
# Bundle a relocatable Tesseract OCR runtime into desktop/ocr-runtime for the
# Linux AppImage, laid out as the macOS and Windows bundles are:
#
#   bin/tesseract          a wrapper that finds lib/ from wherever it sits
#   libexec/tesseract      the real executable
#   lib/*.so*              every shared library it needs, except glibc's own
#   share/tessdata/        English (and orientation, if present) language data
#
# The backend runs `tesseract` from PATH (pytesseract), with ocr-runtime/bin
# first and TESSDATA_PREFIX set (desktopEnvironment in src/runtime.cjs). The
# wrapper sets LD_LIBRARY_PATH for Tesseract only, so the bundled libraries
# never reach Axcess or Chromium. glibc and the dynamic loader stay the
# host's: an AppImage runs on distros with that glibc or newer, which is why
# the release builds on the oldest Ubuntu it supports.
#
# Install Tesseract first: sudo apt-get install tesseract-ocr tesseract-ocr-eng
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This script bundles Tesseract for Linux builds." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DESTINATION="$DESKTOP_DIR/ocr-runtime"
TESSERACT="$(command -v tesseract || true)"
if [[ -z "$TESSERACT" ]]; then
  echo "Tesseract is required to build the Linux desktop app (sudo apt-get install tesseract-ocr tesseract-ocr-eng)." >&2
  exit 1
fi
TESSERACT="$(readlink -f "$TESSERACT")"

# The language folder: Tesseract 5 names it in --list-langs ('List of
# available languages in "/usr/share/tessdata/"'); Tesseract 4, as on
# Ubuntu 22.04, does not, so the usual places are tried after it.
TESSDATA_SOURCE=""
shopt -s nullglob
for candidate in \
  "$(tesseract --list-langs 2>&1 | sed -n 's/.*"\(.*\)".*/\1/p' | head -n 1)" \
  "${TESSDATA_PREFIX:-}" \
  /usr/share/tesseract-ocr/*/tessdata \
  /usr/share/tessdata \
  /usr/local/share/tessdata; do
  candidate="${candidate%/}"
  if [[ -n "$candidate" && -f "$candidate/eng.traineddata" ]]; then
    TESSDATA_SOURCE="$candidate"
    break
  fi
done
shopt -u nullglob
if [[ -z "$TESSDATA_SOURCE" ]]; then
  echo "Tesseract English language data is missing (sudo apt-get install tesseract-ocr-eng)." >&2
  exit 1
fi

# A generated, narrowly scoped build folder beneath desktop/.
rm -rf "$DESTINATION"
mkdir -p "$DESTINATION/bin" "$DESTINATION/libexec" "$DESTINATION/lib" "$DESTINATION/share/tessdata"
cp "$TESSERACT" "$DESTINATION/libexec/tesseract"
for language in eng osd; do
  if [[ -f "$TESSDATA_SOURCE/$language.traineddata" ]]; then
    cp "$TESSDATA_SOURCE/$language.traineddata" "$DESTINATION/share/tessdata/"
  fi
done

# Every library ldd resolves, followed through symlinks, except glibc's
# own, which must match the host's dynamic loader.
ldd "$TESSERACT" | awk '/=> \// { print $3 }' | while IFS= read -r library; do
  case "$(basename "$library")" in
    libc.so.*|libm.so.*|libpthread.so.*|libdl.so.*|librt.so.*|libresolv.so.*|ld-linux*.so.*|libmvec.so.*)
      continue
      ;;
  esac
  cp -L "$library" "$DESTINATION/lib/"
done

cat > "$DESTINATION/bin/tesseract" <<'WRAPPER'
#!/bin/sh
# Axcess's bundled Tesseract: run the real executable with the libraries
# bundled beside it. See desktop/scripts/bundle-tesseract-linux.sh.
here="$(dirname "$(readlink -f "$0")")"
LD_LIBRARY_PATH="$here/../lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" exec "$here/../libexec/tesseract" "$@"
WRAPPER
chmod 755 "$DESTINATION/bin/tesseract" "$DESTINATION/libexec/tesseract"
chmod 644 "$DESTINATION/lib/"*

# The bundle must run on its own: no system Tesseract on PATH, only its data.
env -i PATH=/usr/bin:/bin TESSDATA_PREFIX="$DESTINATION/share/tessdata" \
  "$DESTINATION/bin/tesseract" --list-langs | grep -qx eng
echo "Bundled relocatable Tesseract at $DESTINATION ($(ls "$DESTINATION/lib" | wc -l) libraries)"
