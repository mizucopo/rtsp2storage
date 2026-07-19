#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
resolver="${repo_root}/scripts/resolve-release-version.sh"
test_root="$(mktemp -d)"
trap 'rm -rf "${test_root}"' EXIT

work_dir="${test_root}/valid-version"
mkdir -p "${work_dir}"
printf '%s\n' 'v1.2.2' > "${work_dir}/version"

(
  cd "${work_dir}"
  IMAGE_REPOSITORY="mizucopo/rtsp2storage" \
    GITHUB_OUTPUT="${work_dir}/github-output" \
    "${resolver}"
)

grep -Fx 'version=v1.2.2' "${work_dir}/github-output" >/dev/null
grep -Fx 'release_tag=v1.2.2' "${work_dir}/github-output" >/dev/null
grep -Fx 'image=mizucopo/rtsp2storage:v1.2.2' "${work_dir}/github-output" >/dev/null

echo "ok: valid version resolves release outputs"

work_dir="${test_root}/unsafe-version"
mkdir -p "${work_dir}"
# shellcheck disable=SC2016 # The literal command substitution is the unsafe input under test.
printf '%s\n' '$(touch should-not-run)' > "${work_dir}/version"

if (
  cd "${work_dir}"
  IMAGE_REPOSITORY="mizucopo/rtsp2storage" \
    GITHUB_OUTPUT="${work_dir}/github-output" \
    "${resolver}"
); then
  echo "unsafe version was accepted" >&2
  exit 1
fi

echo "ok: unsafe version is rejected"

work_dir="${test_root}/multiline-version"
mkdir -p "${work_dir}"
printf '%s\n%s\n' 'v1.2.2' 'v2.0.0' > "${work_dir}/version"

if (
  cd "${work_dir}"
  IMAGE_REPOSITORY="mizucopo/rtsp2storage" \
    GITHUB_OUTPUT="${work_dir}/github-output" \
    "${resolver}"
) 2> "${work_dir}/error"; then
  echo "multiline version was accepted" >&2
  exit 1
fi

grep -Fx 'version must contain exactly one line.' "${work_dir}/error" >/dev/null

echo "ok: multiline version is rejected"
