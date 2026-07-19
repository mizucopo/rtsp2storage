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
  local version_image_exists="$4"
  local version_image_digest="$5"
  local latest_image_exists="$6"
  local latest_image_digest="$7"
  local release_complete="$8"
  local create_tag="$9"
  local publish_version_image="${10}"
  local repair_latest="${11}"
  local create_release="${12}"
  local output_file="${test_root}/${case_name}.output"

  TAG_EXISTS="${tag_exists}" \
    RELEASE_EXISTS="${release_exists}" \
    VERSION_IMAGE_EXISTS="${version_image_exists}" \
    VERSION_IMAGE_DIGEST="${version_image_digest}" \
    LATEST_IMAGE_EXISTS="${latest_image_exists}" \
    LATEST_IMAGE_DIGEST="${latest_image_digest}" \
    GITHUB_OUTPUT="${output_file}" \
    "${resolver}"

  grep -Fx "release_complete=${release_complete}" "${output_file}" >/dev/null
  grep -Fx "create_tag=${create_tag}" "${output_file}" >/dev/null
  grep -Fx "publish_version_image=${publish_version_image}" "${output_file}" >/dev/null
  grep -Fx "repair_latest=${repair_latest}" "${output_file}" >/dev/null
  grep -Fx "create_release=${create_release}" "${output_file}" >/dev/null
}

assert_invalid_state() {
  local case_name="$1"
  local tag_exists="$2"
  local release_exists="$3"
  local version_image_exists="$4"
  local version_image_digest="$5"
  local latest_image_exists="$6"
  local latest_image_digest="$7"
  local expected_error="$8"
  local error_file="${test_root}/${case_name}.error"

  if TAG_EXISTS="${tag_exists}" \
    RELEASE_EXISTS="${release_exists}" \
    VERSION_IMAGE_EXISTS="${version_image_exists}" \
    VERSION_IMAGE_DIGEST="${version_image_digest}" \
    LATEST_IMAGE_EXISTS="${latest_image_exists}" \
    LATEST_IMAGE_DIGEST="${latest_image_digest}" \
    GITHUB_OUTPUT="${test_root}/${case_name}.output" \
    "${resolver}" 2> "${error_file}"; then
    echo "invalid state ${case_name} was accepted" >&2
    exit 1
  fi

  grep -Fx "${expected_error}" "${error_file}" >/dev/null
}

assert_state initial false false false '' true sha256:old false true true false true
echo "ok: initial release creates tag before publishing and releasing"

assert_state tag_only_image_missing true false false '' true sha256:old false false true false true
echo "ok: tag-only release rebuilds the missing image"

assert_state tag_and_images true false true sha256:new true sha256:new false false false false true
echo "ok: tag and image state creates the missing release"

assert_state latest_missing true false true sha256:new false '' false false false true true
echo "ok: missing latest tag is repaired before release"

assert_state latest_stale true false true sha256:new true sha256:old false false false true true
echo "ok: stale latest tag is repaired before release"

assert_state completed true true true sha256:new true sha256:new true false false false false
echo "ok: completed release is a no-op"

assert_state completed_image_missing true true false '' true sha256:old false false true false false
echo "ok: completed metadata rebuilds a missing version image"

assert_state completed_latest_stale true true true sha256:new true sha256:old false false false true false
echo "ok: completed metadata repairs a stale latest tag"

assert_invalid_state release_only false true false '' false '' \
  'GitHub Release exists without the matching git tag.'
echo "ok: release-only state fails closed"

assert_invalid_state image_only false false true sha256:new true sha256:new \
  'Docker image exists without the matching git tag.'
echo "ok: image-only state fails closed"
