#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${AGENT_ROOT}"

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

echo "Built macOS app at agent_daemon/dist/PersonalAIOpsAgent.app"
echo "Built macOS installer at agent_daemon/dist/PersonalAIOpsAgent.pkg"

