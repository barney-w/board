#!/usr/bin/env bash
# Generate an encrypted .board-pass file for a developer
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ui.sh
source "${SCRIPT_DIR}/lib/ui.sh"

NAME="${1:?Usage: export-bundle.sh <name> [env] [location] [region]}"
ENV="${2:-personal}"
LOCATION="${3:-australiaeast}"
REGION="${4:-aue}"

# Derived names (must match extension/src/config.ts naming)
KEY_PATH="$HOME/.ssh/devvm-${NAME}"
HOSTNAME="devvm-${NAME}.${LOCATION}.cloudapp.azure.com"
RG="rg-${ENV}-${REGION}-devvm"
VM_NAME="vm-${ENV}-${REGION}-devvm-${NAME}"
OUTPUT_FILE="${NAME}.board-pass"

# ── Preflight checks ──

if [[ ! -f "$KEY_PATH" || ! -f "${KEY_PATH}.pub" ]]; then
    ui_error "SSH key not found. Run: just generate-key ${NAME}"
    exit 1
fi

if ! command -v node &>/dev/null; then
    ui_error "Node.js is required for board-pass encryption."
    exit 1
fi

if ! command -v jq &>/dev/null; then
    ui_error "jq is required to build the payload."
    exit 1
fi

# ── Fetch browser IDE details from VM ──

TUNNEL_URL=""

# Only fetch if we can SSH to the VM
if ssh -i "$KEY_PATH" -o ConnectTimeout=5 -o BatchMode=yes "devuser@${HOSTNAME}" "true" 2>/dev/null; then
    TUNNEL_URL=$(ssh -i "$KEY_PATH" "devuser@${HOSTNAME}" \
        'cat ~/.board/tunnel-url 2>/dev/null' || echo "")
fi

# ── Passphrase (non-interactive via BOARD_PASSPHRASE env var, or prompt) ──

PASS="${BOARD_PASSPHRASE:-}"
if [[ -z "$PASS" ]]; then
    PASS=$(ui_input_secret "Passphrase for board pass")
    if [[ -z "$PASS" ]]; then
        ui_error "Passphrase cannot be empty"
        exit 1
    fi
    PASS2=$(ui_input_secret "Confirm passphrase")
    if [[ "$PASS" != "$PASS2" ]]; then
        ui_error "Passphrases don't match"
        exit 1
    fi
fi

# Validate passphrase strength
if [[ ${#PASS} -lt 8 ]]; then
    ui_error "Passphrase must be at least 8 characters (got ${#PASS})"
    exit 1
fi

# ── Build payload JSON ──

TTL_DAYS="${BOARD_PASS_TTL_DAYS:-30}"
ISSUED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# macOS date vs GNU date for expiry calculation
VALID_UNTIL=$(date -u -v+"${TTL_DAYS}"d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || \
    date -u -d "+${TTL_DAYS} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || \
    echo "")

PAYLOAD=$(jq -n \
    --arg name "$NAME" \
    --arg env "$ENV" \
    --arg region "$LOCATION" \
    --arg regionShort "$REGION" \
    --arg hostname "$HOSTNAME" \
    --arg username "devuser" \
    --arg authMethod "ssh-key" \
    --rawfile privKey "$KEY_PATH" \
    --rawfile pubKey "${KEY_PATH}.pub" \
    --arg rg "$RG" \
    --arg vmName "$VM_NAME" \
    --arg tunnelUrl "$TUNNEL_URL" \
    --arg issuedAt "$ISSUED_AT" \
    --arg validUntil "$VALID_UNTIL" \
    '{developerName:$name, environment:$env, region:$region, regionShort:$regionShort,
      hostname:$hostname, username:$username, authMethod:$authMethod,
      sshPrivateKey:$privKey, sshPublicKey:$pubKey, resourceGroup:$rg, vmName:$vmName,
      issuedAt:$issuedAt, validUntil:$validUntil,
      browserIde: {
        codeServer: {
          localUrl: "http://localhost:8080",
          sshTunnelCommand: ("ssh -L 8080:localhost:8080 -N devuser@" + $hostname)
        },
        vscodeTunnel: {
          url: $tunnelUrl,
          auth: "github"
        }
      }}')

# ── Encrypt with AES-256-GCM (matches extension/src/bundle.ts decryptBundle) ──

node -e "
const crypto = require('crypto');
const passphrase = process.argv[1];
const payload = process.argv[2];
const salt = crypto.randomBytes(16);
const iv = crypto.randomBytes(12);
const key = crypto.pbkdf2Sync(passphrase, salt, 100000, 32, 'sha256');
const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
let encrypted = cipher.update(payload, 'utf8');
encrypted = Buffer.concat([encrypted, cipher.final()]);
const tag = cipher.getAuthTag();
const bundle = {
  version: 2,
  format: 'board-pass',
  salt: salt.toString('base64'),
  iv: iv.toString('base64'),
  ciphertext: encrypted.toString('base64'),
  tag: tag.toString('base64')
};
console.log(JSON.stringify(bundle, null, 2));
" "$PASS" "$PAYLOAD" > "$OUTPUT_FILE"

# ── Build the starter kit zip ──

TEMPLATE_DIR="${SCRIPT_DIR}/templates"
EXT_DIR="${SCRIPT_DIR}/../extension"
KIT_DIR=$(mktemp -d)
KIT_NAME="${NAME}-board"
KIT_STAGE="${KIT_DIR}/${KIT_NAME}"
KIT_ZIP="${KIT_NAME}.zip"

mkdir -p "$KIT_STAGE"

# Build the extension .vsix (if not already built or outdated)
# Read version from package.json to find the correct filename
EXT_PKG_VERSION=$(node -p "require('${EXT_DIR}/package.json').version" 2>/dev/null || echo "0.1.0")
EXT_PKG_NAME=$(node -p "require('${EXT_DIR}/package.json').name" 2>/dev/null || echo "board")
VSIX_FILE="${EXT_DIR}/${EXT_PKG_NAME}-${EXT_PKG_VERSION}.vsix"

if [[ ! -f "$VSIX_FILE" ]]; then
    # Also check for any existing .vsix that might have a different version
    VSIX_FILE=$(find "$EXT_DIR" -maxdepth 1 -name '*.vsix' | head -1)
fi

if [[ -z "$VSIX_FILE" || ! -f "$VSIX_FILE" ]]; then
    ui_info "Building Board extension..."
    if ! (cd "$EXT_DIR" && npm install --silent 2>/dev/null && npm run build:prod --silent && npx @vscode/vsce package --no-dependencies --silent) 2>/dev/null; then
        ui_error "Failed to build extension. Run 'cd extension && npm install' first."
        rm -rf "$KIT_DIR"
        exit 1
    fi
    # Find whatever vsix was produced
    VSIX_FILE=$(find "$EXT_DIR" -maxdepth 1 -name '*.vsix' | head -1)
fi

if [[ -z "$VSIX_FILE" || ! -f "$VSIX_FILE" ]]; then
    ui_error "No .vsix found. Build the extension first: cd extension && npm run package"
    rm -rf "$KIT_DIR"
    exit 1
fi

# Generate Quick Start PDF if python3 + fpdf2 are available
GUIDE_PDF="$TEMPLATE_DIR/Board Quick Start.pdf"
if python3 -c "import fpdf" 2>/dev/null; then
    python3 "$SCRIPT_DIR/generate-guide-pdf.py" "$GUIDE_PDF" 2>/dev/null || true
fi

# Assemble the kit
cp "$OUTPUT_FILE" "$KIT_STAGE/"
cp "$VSIX_FILE" "$KIT_STAGE/board.vsix"
cp "$TEMPLATE_DIR/Setup Board.command" "$KIT_STAGE/"
cp "$TEMPLATE_DIR/Setup Board.cmd" "$KIT_STAGE/"
if [[ -f "$GUIDE_PDF" ]]; then
    cp "$GUIDE_PDF" "$KIT_STAGE/"
fi
chmod +x "$KIT_STAGE/Setup Board.command"

# Create the zip
(cd "$KIT_DIR" && zip -rq "$OLDPWD/$KIT_ZIP" "$KIT_NAME")
rm -rf "$KIT_DIR"

# Clean up the standalone .board-pass (it's in the zip now)
rm -f "$OUTPUT_FILE"

echo ""
ui_boarding_pass \
    "$NAME" \
    "$LOCATION" \
    "$REGION" \
    "$ENV" \
    "$HOSTNAME" \
    "ssh-key" \
    "$ISSUED_AT" \
    "$VALID_UNTIL" \
    "$KIT_ZIP"

ui_info "Send ${_bold}${KIT_ZIP}${_reset} to ${NAME}."
ui_info "Share the passphrase separately (in person, different channel)."
echo ""
ui_info "They unzip it, double-click 'Setup Board', enter the passphrase — done."

if [[ -n "$TUNNEL_URL" ]]; then
    echo ""
    ui_info "Browser access: $TUNNEL_URL"
fi
