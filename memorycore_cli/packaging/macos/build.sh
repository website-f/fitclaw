#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORYCORE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_ROOT="$(cd "${MEMORYCORE_ROOT}/.." && pwd)"
APP_MAIN="${REPO_ROOT}/app/main.py"
DIST_DIR="${MEMORYCORE_ROOT}/dist"
BUILD_DIR="${MEMORYCORE_ROOT}/build-output"
STAGE_ROOT="${BUILD_DIR}/macos-stage"

VERSION="${VERSION:-}"
SERVER_URL="${SERVER_URL:-http://localhost:8000}"
USER_ID="${USER_ID:-fitclaw}"
WAKE_NAME="${WAKE_NAME:-jarvis}"

normalize_wake() {
  local value
  value="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
  if [[ -z "${value}" ]]; then
    value="jarvis"
  fi
  printf '%s' "${value}"
}

if [[ -z "${VERSION}" ]]; then
  VERSION="$(grep -Eo 'version="[^"]+"' "${APP_MAIN}" | head -n1 | cut -d'"' -f2)"
fi

WAKE_NAME="$(normalize_wake "${WAKE_NAME}")"

mkdir -p "${DIST_DIR}" "${BUILD_DIR}"
rm -rf "${STAGE_ROOT}"
rm -f "${DIST_DIR}"/MemoryCore-* "${DIST_DIR}/memorycore-bin" "${DIST_DIR}/memorycore" "${DIST_DIR}/hey" "${DIST_DIR}/${WAKE_NAME}" "${DIST_DIR}/Install MemoryCore.command" "${DIST_DIR}/README.txt"

cd "${MEMORYCORE_ROOT}"

CGO_ENABLED=0 GOOS=darwin GOARCH=amd64 go build -trimpath -ldflags "-s -w" -o "${BUILD_DIR}/memorycore-amd64" .
CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -trimpath -ldflags "-s -w" -o "${BUILD_DIR}/memorycore-arm64" .
lipo -create -output "${DIST_DIR}/memorycore-bin" "${BUILD_DIR}/memorycore-amd64" "${BUILD_DIR}/memorycore-arm64"
chmod +x "${DIST_DIR}/memorycore-bin"

cat > "${DIST_DIR}/memorycore" <<EOF
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
SERVER_URL="${SERVER_URL}"
MEMORYCORE_USER="${USER_ID}"
"\$SCRIPT_DIR/memorycore-bin" --server-url "\$SERVER_URL" --user-id "\$MEMORYCORE_USER" "\$@"
EOF

cat > "${DIST_DIR}/hey" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ \$# -lt 1 ]]; then
  echo "Usage: hey ${WAKE_NAME} remember this whole thing"
  exit 1
fi
if [[ "\$1" != "${WAKE_NAME}" ]]; then
  echo "Wake name mismatch. Expected ${WAKE_NAME}."
  exit 1
fi
shift
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
SERVER_URL="${SERVER_URL}"
MEMORYCORE_USER="${USER_ID}"
"\$SCRIPT_DIR/memorycore-bin" --server-url "\$SERVER_URL" --user-id "\$MEMORYCORE_USER" "\$@"
EOF

cat > "${DIST_DIR}/${WAKE_NAME}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ \$# -lt 1 ]]; then
  echo "Usage: ${WAKE_NAME} remember this whole thing"
  exit 1
fi
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
SERVER_URL="${SERVER_URL}"
MEMORYCORE_USER="${USER_ID}"
"\$SCRIPT_DIR/memorycore-bin" --server-url "\$SERVER_URL" --user-id "\$MEMORYCORE_USER" "\$@"
EOF

cat > "${DIST_DIR}/Install MemoryCore.command" <<EOF
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="\$HOME/.local/share/memorycore"
BIN_DIR="\$HOME/.local/bin"
mkdir -p "\$INSTALL_ROOT" "\$BIN_DIR"
cp "\$SCRIPT_DIR/memorycore-bin" "\$INSTALL_ROOT/memorycore-bin"
cp "\$SCRIPT_DIR/memorycore" "\$BIN_DIR/memorycore"
cp "\$SCRIPT_DIR/hey" "\$BIN_DIR/hey"
cp "\$SCRIPT_DIR/${WAKE_NAME}" "\$BIN_DIR/${WAKE_NAME}"
cp "\$SCRIPT_DIR/README.txt" "\$INSTALL_ROOT/README.txt"
chmod +x "\$INSTALL_ROOT/memorycore-bin" "\$BIN_DIR/memorycore" "\$BIN_DIR/hey" "\$BIN_DIR/${WAKE_NAME}"
PATH_LINE='export PATH="\$HOME/.local/bin:\$PATH"'
for shell_rc in "\$HOME/.zprofile" "\$HOME/.zshrc" "\$HOME/.bash_profile" "\$HOME/.bashrc"; do
  if [[ ! -f "\$shell_rc" ]]; then
    touch "\$shell_rc"
  fi
  if ! grep -Fq "\$PATH_LINE" "\$shell_rc"; then
    printf '\n%s\n' "\$PATH_LINE" >> "\$shell_rc"
  fi
done
echo
echo "MemoryCore was installed into ~/.local/bin and ~/.local/share/memorycore."
echo "Reopen Terminal, then run:"
echo "  ${WAKE_NAME} remember this whole thing"
echo "or"
echo "  hey ${WAKE_NAME} remember this whole thing"
EOF

cat > "${DIST_DIR}/README.txt" <<EOF
MemoryCore Portable Bundle
==========================

Server URL: ${SERVER_URL}
User ID: ${USER_ID}
Wake name: ${WAKE_NAME}

Quick install:
1. Extract this zip anywhere.
2. Double-click Install MemoryCore.command
3. Reopen Terminal.
4. Run:
   ${WAKE_NAME} remember this whole thing
   or
   hey ${WAKE_NAME} remember this whole thing

Behavior:
- The command saves project memory to your MemoryCore server.
- It also writes a local MEMORYCORE.md in the current project folder by default.
- If you only want cloud save later, the hidden engine supports --no-write-local.
EOF

chmod +x "${DIST_DIR}/memorycore" "${DIST_DIR}/hey" "${DIST_DIR}/${WAKE_NAME}" "${DIST_DIR}/Install MemoryCore.command"

(
  cd "${DIST_DIR}"
  zip -q -r "MemoryCore-${VERSION}-macos-portable.zip" "memorycore-bin" "memorycore" "hey" "${WAKE_NAME}" "Install MemoryCore.command" "README.txt"
)

mkdir -p "${STAGE_ROOT}/usr/local/libexec/memorycore" "${STAGE_ROOT}/usr/local/bin" "${STAGE_ROOT}/usr/local/share/memorycore"
cp "${DIST_DIR}/memorycore-bin" "${STAGE_ROOT}/usr/local/libexec/memorycore/memorycore-bin"
cp "${DIST_DIR}/README.txt" "${STAGE_ROOT}/usr/local/share/memorycore/README.txt"

cat > "${STAGE_ROOT}/usr/local/bin/memorycore" <<EOF
#!/usr/bin/env bash
set -euo pipefail
SERVER_URL="${SERVER_URL}"
MEMORYCORE_USER="${USER_ID}"
"/usr/local/libexec/memorycore/memorycore-bin" --server-url "\$SERVER_URL" --user-id "\$MEMORYCORE_USER" "\$@"
EOF

cat > "${STAGE_ROOT}/usr/local/bin/hey" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ \$# -lt 1 ]]; then
  echo "Usage: hey ${WAKE_NAME} remember this whole thing"
  exit 1
fi
if [[ "\$1" != "${WAKE_NAME}" ]]; then
  echo "Wake name mismatch. Expected ${WAKE_NAME}."
  exit 1
fi
shift
SERVER_URL="${SERVER_URL}"
MEMORYCORE_USER="${USER_ID}"
"/usr/local/libexec/memorycore/memorycore-bin" --server-url "\$SERVER_URL" --user-id "\$MEMORYCORE_USER" "\$@"
EOF

cat > "${STAGE_ROOT}/usr/local/bin/${WAKE_NAME}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ \$# -lt 1 ]]; then
  echo "Usage: ${WAKE_NAME} remember this whole thing"
  exit 1
fi
SERVER_URL="${SERVER_URL}"
MEMORYCORE_USER="${USER_ID}"
"/usr/local/libexec/memorycore/memorycore-bin" --server-url "\$SERVER_URL" --user-id "\$MEMORYCORE_USER" "\$@"
EOF

chmod +x "${STAGE_ROOT}/usr/local/libexec/memorycore/memorycore-bin" "${STAGE_ROOT}/usr/local/bin/memorycore" "${STAGE_ROOT}/usr/local/bin/hey" "${STAGE_ROOT}/usr/local/bin/${WAKE_NAME}"

pkgbuild \
  --root "${STAGE_ROOT}" \
  --identifier "com.fitclaw.memorycore" \
  --version "${VERSION}" \
  --install-location "/" \
  "${DIST_DIR}/MemoryCore-${VERSION}-macos.pkg"

echo "Built macOS portable bundle at memorycore_cli/dist/MemoryCore-${VERSION}-macos-portable.zip"
echo "Built macOS installer at memorycore_cli/dist/MemoryCore-${VERSION}-macos.pkg"
