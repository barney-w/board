#!/usr/bin/env bash
set -euo pipefail

HOST="${1:?Usage: validate-deployment.sh <hostname> [ssh-key-path]}"
KEY_PATH="${2:-}"
USER="devuser"

echo "=== Board Smoke Test: $HOST ==="

run_remote() {
    local ssh_args=(
        -o ConnectTimeout=10
        -o StrictHostKeyChecking=accept-new
        -o BatchMode=yes
        -o LogLevel=ERROR
    )
    if [[ -n "$KEY_PATH" ]]; then
        ssh_args+=(-i "$KEY_PATH")
    fi
    # shellcheck disable=SC2029 # intentional client-side expansion for SSH command
    ssh "${ssh_args[@]}" "$USER@$HOST" "$1"
}

# Clear stale host keys (VM may have been redeployed with a new key)
ssh-keygen -R "$HOST" &>/dev/null || true

# Verify connectivity
echo "Connecting to board..."
if ! run_remote "true" 2>/dev/null; then
    echo "  ✗ Cannot connect to board. Ensure it's running and SSH key is correct."
    echo ""
    echo "  Diagnostic:"
    ssh -o ConnectTimeout=5 -o BatchMode=yes ${KEY_PATH:+-i "$KEY_PATH"} -v \
        "$USER@$HOST" "true" 2>&1 | grep -E '(Connection|connect|refused|timed|key|Host key)' | head -5 | sed 's/^/    /'
    exit 1
fi
echo "  ✓ Connected"

# Check cloud-init status (fail fast instead of blind 10-min wait)
echo "Checking cloud-init status..."
CI_STATUS=$(run_remote "cloud-init status 2>/dev/null" 2>/dev/null) || CI_STATUS="unknown"
# Normalize: newer cloud-init (Ubuntu 24.04+) outputs just "done", older outputs "status: done"
CI_STATUS_CLEAN=$(echo "$CI_STATUS" | grep -oE '(running|done|error|degraded|disabled)' | head -1)
if [[ "$CI_STATUS_CLEAN" == "running" ]]; then
    echo "  Cloud-init is still running. Wait for it to finish first:"
    echo "    just cloud-init-status <name>"
    echo "  Then re-run: just smoke-test <name>"
    exit 1
elif [[ "$CI_STATUS_CLEAN" == "error" || "$CI_STATUS_CLEAN" == "degraded" ]]; then
    echo "  ⚠ Cloud-init reported errors. Some checks may fail."
    echo ""
elif [[ "$CI_STATUS_CLEAN" == "done" ]]; then
    echo "  ✓ Cloud-init complete"
else
    echo "  ⚠ Could not determine cloud-init status. Proceeding anyway."
fi

# Check tools
checks=(
    "git --version"
    "python3 --version"
    "uv --version"
    "node --version"
    "npm --version"
    "docker --version"
    "docker compose version"
    "az version --query '\"azure-cli\"' -o tsv"
    "just --version"
    "nvim --version | head -1"
    "gh --version | head -1"
    "jq --version"
    "pnpm --version"
    "yq --version"
)

PASS=0
FAIL=0

for cmd in "${checks[@]}"; do
    if output=$(run_remote "$cmd" 2>&1); then
        echo "  ✓ $cmd → $output"
        ((PASS++))
    else
        echo "  ✗ $cmd → FAILED"
        ((FAIL++))
    fi
done

# Check Docker without sudo
echo ""
echo "Checking Docker runs without sudo..."
if run_remote "docker run --rm hello-world" &>/dev/null; then
    echo "  ✓ Docker runs without sudo"
    ((PASS++))
else
    echo "  ✗ Docker requires sudo or is not working"
    ((FAIL++))
fi

# Check SSH hardening
echo ""
echo "Checking SSH hardening..."
sshd_config=$(run_remote "sudo cat /etc/ssh/sshd_config")
for setting in "PermitRootLogin no" "PasswordAuthentication no" "X11Forwarding no" "MaxAuthTries 3"; do
    if echo "$sshd_config" | grep -q "^$setting"; then
        echo "  ✓ $setting"
        ((PASS++))
    else
        echo "  ✗ $setting NOT FOUND"
        ((FAIL++))
    fi
done

# Check cloud-init artifacts (write_files + home ownership)
echo ""
echo "Checking cloud-init artifacts..."
for artifact_check in \
    "test -x ~/setup-me.sh:setup-me.sh exists and is executable" \
    "test -f ~/.board/config:.board/config exists" \
    "stat -c '%U' /home/devuser 2>/dev/null | grep -q devuser || ls -ld /home/devuser | grep -q devuser:/home/devuser owned by devuser" \
    "test -f ~/.config/systemd/user/board-check.timer:board-check systemd timer installed"; do
    check_cmd="${artifact_check%%:*}"
    check_desc="${artifact_check#*:}"
    if run_remote "$check_cmd" 2>/dev/null; then
        echo "  ✓ $check_desc"
        ((PASS++))
    else
        echo "  ✗ $check_desc"
        ((FAIL++))
    fi
done

# Check project health (if provisioned)
echo ""
echo "Checking project health..."
if run_remote "test -f ~/projects/.board/check.sh" 2>/dev/null; then
    check_output=$(run_remote "bash ~/projects/.board/check.sh" 2>&1) || true
    # shellcheck disable=SC2001 # sed is clearer than ${//} for line-prefix insertion
    echo "$check_output" | sed 's/^/  /'
    # Count check results
    check_pass=$(echo "$check_output" | grep -c "✓" || true)
    check_fail=$(echo "$check_output" | grep -c "✗" || true)
    PASS=$((PASS + check_pass))
    FAIL=$((FAIL + check_fail))
else
    echo "  No project provisioning detected (check script not found)"
    echo "  This is normal if projects weren't selected during setup."
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && echo "All checks passed." || exit 1
