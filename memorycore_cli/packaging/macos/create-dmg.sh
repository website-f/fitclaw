#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORYCORE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_ROOT="$(cd "${MEMORYCORE_ROOT}/.." && pwd)"
APP_MAIN="${REPO_ROOT}/app/main.py"
DMG_ROOT="${MEMORYCORE_ROOT}/build-output/dmgroot"
DIST_DIR="${MEMORYCORE_ROOT}/dist"

VERSION="${VERSION:-}"
if [[ -z "${VERSION}" ]]; then
  VERSION="$(grep -Eo 'version="[^"]+"' "${APP_MAIN}" | head -n1 | cut -d'"' -f2)"
fi

mkdir -p "${DMG_ROOT}"
rm -f "${DMG_ROOT}/MemoryCore.pkg" "${DMG_ROOT}/README.txt"
cp "${DIST_DIR}/MemoryCore-${VERSION}-macos.pkg" "${DMG_ROOT}/MemoryCore.pkg"
cp "${DIST_DIR}/README.txt" "${DMG_ROOT}/README.txt"

hdiutil create \
  -volname "MemoryCore" \
  -srcfolder "${DMG_ROOT}" \
  -ov \
  -format UDZO \
  "${DIST_DIR}/MemoryCore-${VERSION}-macos.dmg"

echo "Built macOS DMG at memorycore_cli/dist/MemoryCore-${VERSION}-macos.dmg"
