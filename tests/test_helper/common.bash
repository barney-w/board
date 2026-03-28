# Common test setup — sourced by all .bats files via load 'test_helper/common'
PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")" && pwd)"
export PROJECT_ROOT

# Load bats helpers
load "${BATS_TEST_DIRNAME}/test_helper/bats-support/load"
load "${BATS_TEST_DIRNAME}/test_helper/bats-assert/load"

# Ensure non-interactive mode
export USE_GUM=false
export BOARD_NON_INTERACTIVE=1
