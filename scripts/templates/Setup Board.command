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

# Install extension
echo "  Installing Board extension..."
code --install-extension "$VSIX" --force 2>/dev/null
echo "  Done."
echo ""

# Open the board pass in VS Code (triggers the import flow)
echo "  Opening your board pass in VS Code..."
code "$PASS"
echo ""
echo "  VS Code should now be asking for your passphrase."
echo "  Enter the passphrase your team lead gave you."
echo ""
read -p "  Press Enter to close this window..."
