#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VERSION_FILE="${AGENT_ROOT}/VERSION"
VERSION="0.1.0"

if [[ -f "${VERSION_FILE}" ]]; then
  VERSION="$(tr -d '[:space:]' < "${VERSION_FILE}")"
fi

cd "${AGENT_ROOT}"

rm -rf dist/PersonalAIOpsAgent*.app
rm -f dist/PersonalAIOpsAgent*.pkg dist/PersonalAIOpsAgent*.dmg

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt -r build-requirements.txt

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name PersonalAIOpsAgent \
  --distpath dist \
  --workpath build-output/pyinstaller \
  --specpath build-output/spec \
  agent_daemon.py

pkgbuild \
  --component "dist/PersonalAIOpsAgent.app" \
  --install-location "/Applications" \
  "dist/PersonalAIOpsAgent.pkg"

mv "dist/PersonalAIOpsAgent.app" "dist/PersonalAIOpsAgent-${VERSION}-macos.app"
mv "dist/PersonalAIOpsAgent.pkg" "dist/PersonalAIOpsAgent-${VERSION}-macos.pkg"

echo "Built macOS app at agent_daemon/dist/PersonalAIOpsAgent-${VERSION}-macos.app"
echo "Built macOS installer at agent_daemon/dist/PersonalAIOpsAgent-${VERSION}-macos.pkg"
