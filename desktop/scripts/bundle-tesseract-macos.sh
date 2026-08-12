#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The bundled OCR runtime is currently supported only for macOS builds." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DESTINATION="$DESKTOP_DIR/ocr-runtime"
TESSERACT="$(command -v tesseract || true)"

if [[ -z "$TESSERACT" ]]; then
  echo "Tesseract is required to build the macOS desktop app (brew install tesseract)." >&2
  exit 1
fi

TESSERACT="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$TESSERACT")"
TESSERACT_PREFIX="$(brew --prefix tesseract)"
TESSDATA_SOURCE="$TESSERACT_PREFIX/share/tessdata"
if [[ ! -f "$TESSDATA_SOURCE/eng.traineddata" ]]; then
  echo "Tesseract English language data is missing: $TESSDATA_SOURCE" >&2
  exit 1
fi

# This is a generated, narrowly scoped build directory beneath desktop/.
rm -rf "$DESTINATION"
mkdir -p "$DESTINATION/bin" "$DESTINATION/lib" "$DESTINATION/share/tessdata"
cp "$TESSERACT" "$DESTINATION/bin/tesseract"
cp -R "$TESSDATA_SOURCE/." "$DESTINATION/share/tessdata/"

MANIFEST="$(mktemp -t axcess-tesseract-manifest)"
trap 'rm -f "$MANIFEST"' EXIT

resolve_dependency() {
  local owner="$1"
  local dependency="$2"
  local owner_dir
  owner_dir="$(dirname "$owner")"
  case "$dependency" in
    @loader_path/*)
      printf '%s\n' "$owner_dir/${dependency#@loader_path/}"
      return
      ;;
    @executable_path/*)
      printf '%s\n' "$(dirname "$TESSERACT")/${dependency#@executable_path/}"
      return
      ;;
    @rpath/*)
      local relative="${dependency#@rpath/}"
      if [[ -e "$owner_dir/$relative" ]]; then
        printf '%s\n' "$owner_dir/$relative"
        return
      fi
      while IFS= read -r runtime_path; do
        runtime_path="${runtime_path//@loader_path/$owner_dir}"
        runtime_path="${runtime_path//@executable_path/$(dirname "$TESSERACT")}"
        if [[ -e "$runtime_path/$relative" ]]; then
          printf '%s\n' "$runtime_path/$relative"
          return
        fi
      done < <(otool -l "$owner" | awk '/cmd LC_RPATH/{getline; getline; print $2}')
      ;;
    *)
      printf '%s\n' "$dependency"
      return
      ;;
  esac
  echo "Cannot resolve Tesseract dependency $dependency from $owner" >&2
  exit 1
}

collect_dependencies() {
  local source="$1"
  local canonical
  canonical="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$source")"
  if grep -Fqx "$canonical" "$MANIFEST" 2>/dev/null; then
    return
  fi
  printf '%s\n' "$canonical" >> "$MANIFEST"

  while IFS= read -r dependency; do
    [[ -z "$dependency" ]] && continue
    case "$dependency" in
      /usr/lib/*|/System/Library/*) continue ;;
    esac
    local resolved
    resolved="$(resolve_dependency "$canonical" "$dependency")"
    resolved="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$resolved")"
    local target="$DESTINATION/lib/$(basename "$resolved")"
    if [[ ! -e "$target" ]]; then
      cp "$resolved" "$target"
    fi
    collect_dependencies "$resolved"
  done < <(otool -L "$canonical" | tail -n +2 | sed -E 's/^[[:space:]]*([^[:space:]]+).*/\1/')
}

collect_dependencies "$TESSERACT"

patch_dependencies() {
  local original="$1"
  local target="$2"
  local prefix="$3"
  while IFS= read -r dependency; do
    [[ -z "$dependency" ]] && continue
    case "$dependency" in
      /usr/lib/*|/System/Library/*) continue ;;
    esac
    local resolved
    resolved="$(resolve_dependency "$original" "$dependency")"
    resolved="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$resolved")"
    install_name_tool -change "$dependency" "$prefix/$(basename "$resolved")" "$target"
  done < <(otool -L "$original" | tail -n +2 | sed -E 's/^[[:space:]]*([^[:space:]]+).*/\1/')
}

patch_dependencies "$TESSERACT" "$DESTINATION/bin/tesseract" "@loader_path/../lib"
while IFS= read -r original; do
  [[ "$original" == "$TESSERACT" ]] && continue
  target="$DESTINATION/lib/$(basename "$original")"
  install_name_tool -id "@loader_path/$(basename "$original")" "$target"
  patch_dependencies "$original" "$target" "@loader_path"
done < "$MANIFEST"

chmod 755 "$DESTINATION/bin/tesseract" "$DESTINATION/lib/"*.dylib
codesign --force --sign - "$DESTINATION/lib/"*.dylib
codesign --force --sign - "$DESTINATION/bin/tesseract"

TESSDATA_PREFIX="$DESTINATION/share/tessdata" \
  "$DESTINATION/bin/tesseract" --version >/dev/null
echo "Bundled relocatable Tesseract at $DESTINATION"
