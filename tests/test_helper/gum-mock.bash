# tests/test_helper/gum-mock.bash
# Mock gum — not available in test environment
gum() { return 1; }
export -f gum
