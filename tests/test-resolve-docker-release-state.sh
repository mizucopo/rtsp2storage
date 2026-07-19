#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
resolver="${repo_root}/scripts/resolve-docker-release-state.sh"
test_root="$(mktemp -d)"
trap 'rm -rf "${test_root}"' EXIT

assert_state() {
  local case_name="$1"
  local tag_exists="$2"
  local release_exists="$3"
  local image_exists="$4"
  local release_complete="$5"
  local create_tag="$6"
  local publish_image="$7"
  local create_release="$8"
  local output_file="${test_root}/${case_name}.output"

  TAG_EXISTS="${tag_exists}" \
    RELEASE_EXISTS="${release_exists}" \
    IMAGE_EXISTS="${image_exists}" \
    GITHUB_OUTPUT="${output_file}" \
    "${resolver}"

  grep -Fx "release_complete=${release_complete}" "${output_file}" >/dev/null
  grep -Fx "create_tag=${create_tag}" "${output_file}" >/dev/null
  grep -Fx "publish_image=${publish_image}" "${output_file}" >/dev/null
  grep -Fx "create_release=${create_release}" "${output_file}" >/dev/null
}

assert_invalid_state() {
  local case_name="$1"
  local tag_exists="$2"
  local release_exists="$3"
  local image_exists="$4"
  local expected_error="$5"
  local error_file="${test_root}/${case_name}.error"

  if TAG_EXISTS="${tag_exists}" \
    RELEASE_EXISTS="${release_exists}" \
    IMAGE_EXISTS="${image_exists}" \
    GITHUB_OUTPUT="${test_root}/${case_name}.output" \
    "${resolver}" 2> "${error_file}"; then
    echo "invalid state ${case_name} was accepted" >&2
    exit 1
  fi

  grep -Fx "${expected_error}" "${error_file}" >/dev/null
}

assert_state initial false false false false true true true
echo "ok: initial release creates tag before publishing and releasing"

assert_state tag_only_image_missing true false false false false true true
echo "ok: tag-only release rebuilds the missing image"

assert_state tag_and_image true false true false false false true
echo "ok: tag and image state creates the missing release"

assert_state completed true true '' true false false false
echo "ok: completed release is a no-op"

assert_invalid_state release_only false true '' \
  'GitHub Release exists without the matching git tag.'
echo "ok: release-only state fails closed"

assert_invalid_state image_only false false true \
  'Docker image exists without the matching git tag.'
echo "ok: image-only state fails closed"
