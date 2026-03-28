#!/usr/bin/env bats

setup() {
    load 'test_helper/common'
    source "${PROJECT_ROOT}/scripts/lib/manifest.sh"
}

@test "manifest_get reads project name" {
    run manifest_get "${PROJECT_ROOT}/projects/examples/django-api.project.yaml" '.name'
    assert_output "django-api"
}

@test "manifest_get reads required tools as list" {
    run manifest_get "${PROJECT_ROOT}/projects/examples/django-api.project.yaml" '.requires.tools[]'
    assert_line "python3"
    assert_line "uv"
    assert_line "docker"
}

@test "manifest_get reads repo URL" {
    run manifest_get "${PROJECT_ROOT}/projects/examples/django-api.project.yaml" '.repo'
    assert_success
    assert_output --partial "github.com"
}

@test "manifest_get returns empty for missing field" {
    run manifest_get "${PROJECT_ROOT}/projects/examples/django-api.project.yaml" '.nonexistent'
    assert_output ""
}

@test "all manifests have required fields" {
    for manifest in "${PROJECT_ROOT}"/projects/examples/*.project.yaml; do
        [ -f "$manifest" ] || continue
        name=$(yq eval '.name' "$manifest")
        repo=$(yq eval '.repo' "$manifest")
        path=$(yq eval '.path' "$manifest")
        [[ -n "$name" && "$name" != "null" ]] || fail "$manifest missing .name"
        [[ -n "$repo" && "$repo" != "null" ]] || fail "$manifest missing .repo"
        [[ -n "$path" && "$path" != "null" ]] || fail "$manifest missing .path"
    done
}

@test "django-api manifest requires uv" {
    run manifest_get "${PROJECT_ROOT}/projects/examples/django-api.project.yaml" '.requires.tools[]'
    assert_line "uv"
}

@test "nextjs-app manifest requires pnpm" {
    run manifest_get "${PROJECT_ROOT}/projects/examples/nextjs-app.project.yaml" '.requires.tools[]'
    assert_line "pnpm"
}
