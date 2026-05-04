#!/bin/bash
# Board — installs the extension and opens your board pass
# Just double-click this file to get started!

set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  Setting up Board..."
echo ""

# Check VS Code is installed
if ! command -v code &>/dev/null; then
    echo "  VS Code not found."
    echo ""
    echo "  Install it from: https://code.visualstudio.com"
    echo "  Then re-run this file."
    echo ""
    read -p "  Press Enter to close..."
    exit 1
fi

# Find the .vsix
VSIX="$(find "$DIR" -maxdepth 1 -name '*.vsix' | head -1)"
if [[ -z "$VSIX" ]]; then
    echo "  ERROR: No .vsix file found in this folder."
    read -p "  Press Enter to close..."
    exit 1
fi

# Find the .board-pass
PASS="$(find "$DIR" -maxdepth 1 -name '*.board-pass' | head -1)"
if [[ -z "$PASS" ]]; then
    echo "  ERROR: No .board-pass file found in this folder."
    read -p "  Press Enter to close..."
    exit 1
fi

# Always install the bundled extension with --force so the version shipped
# with this pass wins over any older installed version. Idempotent when the
# bundled version matches what's already installed.
echo "  Installing Board extension..."
if ! code --install-extension "$VSIX" --force; then
    echo "  WARNING: Extension install may have failed."
    echo "  Try opening VS Code and installing $VSIX manually."
fi
echo "  Done."
# Give VS Code time to load the new extension before opening the file
sleep 3
echo ""

# Detect auth method from the board pass JSON (requires python3 or python)
AUTH_METHOD="ssh-key"
if command -v python3 &>/dev/null; then
    AUTH_METHOD="$(python3 -c "import json,sys; d=json.load(open('$PASS')); print(d.get('authMethod','ssh-key'))" 2>/dev/null || echo "ssh-key")"
elif command -v python &>/dev/null; then
    AUTH_METHOD="$(python -c "import json,sys; d=json.load(open('$PASS')); print(d.get('authMethod','ssh-key'))" 2>/dev/null || echo "ssh-key")"
fi

# Open the board pass in a NEW VS Code window. A new window starts a fresh
# extension host that loads the freshly installed extension. Without
# --new-window, any already-open VS Code keeps the previous extension code in
# memory and the import flow can hit the old (encrypted-only) code path —
# producing a passphrase prompt for what should be a plaintext Entra ID pass.
echo "  Opening your board pass in VS Code..."
code --new-window "$PASS"
echo ""
echo "  VS Code is now importing your board pass."
if [[ "$AUTH_METHOD" == "entra-id" ]]; then
    echo "  No passphrase needed — Entra ID handles authentication."
    echo "  Click Connect when VS Code is ready."
else
    echo "  Enter the passphrase your team lead gave you."
fi
echo ""
read -p "  Press Enter to close this window..."
