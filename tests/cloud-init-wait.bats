#!/usr/bin/env bats

setup() {
    load 'test_helper/common'
}

@test "_ci_verify_done checks marker file" {
    grep -q 'test -f.*cloud-init-complete' "${PROJECT_ROOT}/scripts/lib/azure.sh"
}

@test "_ci_verify_done checks docker, node, python3" {
    local verify_section
    verify_section=$(grep -A10 '_ci_verify_done' "${PROJECT_ROOT}/scripts/lib/azure.sh")
    echo "$verify_section" | grep -q 'docker'
    echo "$verify_section" | grep -q 'node'
    echo "$verify_section" | grep -q 'python3'
}

@test "provision engine reads tool requirements from manifests" {
    grep -q "manifest_get.*requires.tools" "${PROJECT_ROOT}/scripts/provision-engine.sh"
}

@test "provision engine retries tool validation (6 attempts, 15s delay)" {
    grep -q 'max_attempts=6' "${PROJECT_ROOT}/scripts/provision-engine.sh"
    grep -q 'retry_delay=15' "${PROJECT_ROOT}/scripts/provision-engine.sh"
}

@test "django-api manifest requires uv (caught by provision engine, not _ci_verify_done)" {
    run yq eval '.requires.tools[]' "${PROJECT_ROOT}/projects/examples/django-api.project.yaml"
    assert_line "uv"
}

@test "nextjs-app manifest requires pnpm" {
    run yq eval '.requires.tools[]' "${PROJECT_ROOT}/projects/examples/nextjs-app.project.yaml"
    assert_line "pnpm"
}

@test "_ci_verify_done has documentation comment about scope" {
    grep -q 'sanity check\|Full manifest-based' "${PROJECT_ROOT}/scripts/lib/azure.sh"
}
