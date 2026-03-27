#!/usr/bin/env bash
# ── Board First-Time Setup Script ──
# NOTE: The canonical copy of this script is embedded in
# infra/cloud-init/cloud-init.yaml (write_files section).
# If you modify this file, update cloud-init.yaml to match.
set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
BOLD='\033[1m'

echo ""
echo -e "${BLUE}${BOLD}╭───────────────────────────────────────────────╮${NC}"
echo -e "${BLUE}${BOLD}│         Board — First-Time Setup               │${NC}"
echo -e "${BLUE}${BOLD}╰───────────────────────────────────────────────╯${NC}"
echo ""

# ── Step 1: Git identity ──
echo -e "${BOLD}Step 1: Git Configuration${NC}"
echo ""

current_name=$(git config --global user.name 2>/dev/null || echo "")
current_email=$(git config --global user.email 2>/dev/null || echo "")

if [[ -n "$current_name" && -n "$current_email" ]]; then
    echo -e "  Git already configured: ${GREEN}$current_name <$current_email>${NC}"
    read -rp "  Change it? (y/N): " change_git
    if [[ "$change_git" != "y" && "$change_git" != "Y" ]]; then
        echo "  Keeping existing config."
    else
        current_name=""
    fi
fi

if [[ -z "$current_name" ]]; then
    read -rp "  Your full name (e.g. Jane Bloggs): " git_name
    read -rp "  Your email: " git_email
    git config --global user.name "$git_name"
    git config --global user.email "$git_email"
    echo -e "  ${GREEN}✓ Git configured: $git_name <$git_email>${NC}"
fi
echo ""

# ── Step 2: SSH key ──
echo -e "${BOLD}Step 2: SSH Key${NC}"
echo ""

if [[ -f ~/.ssh/id_ed25519 ]]; then
    echo -e "  ${GREEN}✓ SSH key already exists.${NC}"
    echo "  Public key:"
    echo ""
    echo -e "  ${YELLOW}$(cat ~/.ssh/id_ed25519.pub)${NC}"
    echo ""
else
    read -rp "  Generate an SSH key for Git hosting? (Y/n): " gen_key
    if [[ "$gen_key" != "n" && "$gen_key" != "N" ]]; then
        email=$(git config --global user.email)
        ssh-keygen -t ed25519 -C "$email" -f ~/.ssh/id_ed25519 -N ""
        echo ""
        echo -e "  ${GREEN}✓ SSH key generated.${NC}"
        echo "  Public key (copy this into your Git host → Settings → SSH Keys):"
        echo ""
        echo -e "  ${YELLOW}$(cat ~/.ssh/id_ed25519.pub)${NC}"
        echo ""

        eval "$(ssh-agent -s)" > /dev/null 2>&1
        ssh-add ~/.ssh/id_ed25519 2>/dev/null
    else
        echo "  Skipping key generation."
    fi
fi
echo ""

# ── Step 3: Tool verification ──
echo -e "${BOLD}Step 3: Verifying Tools${NC}"
echo ""

tools=(
    "git:git --version"
    "Python:python3 --version"
    "uv:uv --version"
    "Node.js:node --version"
    "npm:npm --version"
    "pnpm:pnpm --version"
    "Docker:docker --version"
    "Docker Compose:docker compose version"
    "Azure CLI:az version --query '\"azure-cli\"' -o tsv"
    "just:just --version"
    "neovim:nvim --version | head -1"
    "GitHub CLI:gh --version | head -1"
    "jq:jq --version"
)

pass=0
fail=0

for tool in "${tools[@]}"; do
    name="${tool%%:*}"
    cmd="${tool#*:}"
    if output=$(eval "$cmd" 2>&1); then
        echo -e "  ${GREEN}✓${NC} $name → $output"
        ((pass++))
    else
        echo -e "  ${RED}✗${NC} $name → not found or failed"
        ((fail++))
    fi
done

echo ""

echo -e "  Checking Docker runs without sudo..."
if docker run --rm hello-world &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Docker works without sudo"
    ((pass++))
else
    echo -e "  ${RED}✗${NC} Docker requires sudo — try logging out and back in"
    ((fail++))
fi

echo ""
echo -e "  ${BOLD}Results: ${GREEN}$pass passed${NC}, ${RED}$fail failed${NC}"
echo ""

# ── Step 4: Quick orientation ──
echo -e "${BOLD}Step 4: Your Workspace${NC}"
echo ""
if [[ -f ~/projects/board.code-workspace ]]; then
    echo "  Your projects are ready -- open board.code-workspace in VS Code"
    echo "  Run 'check' any time to verify services are healthy"
    echo ""
    echo "  Useful commands:"
    echo "    check         -> verify all services are running"
    echo "    gs             -> git status"
    echo "    dc up          -> docker compose up"
else
    echo "  Your project directory: ~/projects"
    echo "  To clone a repo:        cd ~/projects && git clone <url>"
    echo ""
    echo "  Useful commands:"
    echo "    gs            -> git status"
    echo "    dc up         -> docker compose up"
    echo "    dc down       -> docker compose down"
    echo "    tmux          -> start a persistent terminal session"
    echo "    help          -> show the full command reference"
fi
echo ""

# ── Signal completion (for VS Code extension first-run detection) ──
touch ~/.setup-me-complete

# ── Done ──
echo -e "${BLUE}${BOLD}╭───────────────────────────────────────────────╮${NC}"
if [[ -f ~/projects/board.code-workspace ]]; then
    echo -e "${BLUE}${BOLD}│  Setup complete. Open board.code-workspace   │${NC}"
    echo -e "${BLUE}${BOLD}│  in VS Code to start coding.                 │${NC}"
else
    echo -e "${BLUE}${BOLD}│  Setup complete. You're ready to code.        │${NC}"
    echo -e "${BLUE}${BOLD}│                                               │${NC}"
    echo -e "${BLUE}${BOLD}│  Next: cd ~/projects && git clone <your-repo> │${NC}"
fi
echo -e "${BLUE}${BOLD}╰───────────────────────────────────────────────╯${NC}"
echo ""
