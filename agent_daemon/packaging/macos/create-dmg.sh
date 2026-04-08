#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DMG_ROOT="${AGENT_ROOT}/build-output/dmgroot"
VERSION_FILE="${AGENT_ROOT}/VERSION"
VERSION="0.1.0"

if [[ -f "${VERSION_FILE}" ]]; then
  VERSION="$(tr -d '[:space:]' < "${VERSION_FILE}")"
fi

mkdir -p "${DMG_ROOT}"
rm -f "${DMG_ROOT}/PersonalAIOpsAgent.pkg"
cp "${AGENT_ROOT}/dist/PersonalAIOpsAgent-${VERSION}-macos.pkg" "${DMG_ROOT}/PersonalAIOpsAgent.pkg"

hdiutil create \
  -volname "PersonalAIOpsAgent" \
  -srcfolder "${DMG_ROOT}" \
  -ov \
  -format UDZO \
  "${AGENT_ROOT}/dist/PersonalAIOpsAgent-${VERSION}-macos.dmg"

echo "Built macOS DMG at agent_daemon/dist/PersonalAIOpsAgent-${VERSION}-macos.dmg"
