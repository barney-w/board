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

# Install extension (skip if already installed to avoid unnecessary reload)
if code --list-extensions 2>/dev/null | grep -qi "barney-w.board"; then
    echo "  Board extension already installed."
else
    echo "  Installing Board extension..."
    if ! code --install-extension "$VSIX"; then
        echo "  WARNING: Extension install may have failed."
        echo "  Try opening VS Code and installing $VSIX manually."
    fi
    echo "  Done."
    # Give VS Code time to load the new extension before opening the file
    sleep 3
fi
echo ""

# Open the board pass in VS Code (triggers the import flow)
echo "  Opening your board pass in VS Code..."
code "$PASS"
echo ""
echo "  VS Code should now be asking for your passphrase."
echo "  Enter the passphrase your team lead gave you."
echo ""
read -p "  Press Enter to close this window..."
