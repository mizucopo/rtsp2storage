#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required.}"
: "${GITHUB_API_URL:?GITHUB_API_URL is required.}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required.}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required.}"
: "${RELEASE_TAG:?RELEASE_TAG is required.}"

response_file="$(mktemp "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/github-release-response.XXXXXX")"
trap 'rm -f "${response_file}"' EXIT

release_url="${GITHUB_API_URL}/repos/${GITHUB_REPOSITORY}/releases/tags/${RELEASE_TAG}"
http_status="$(
  curl \
    --silent \
    --show-error \
    --output "${response_file}" \
    --write-out '%{http_code}' \
    --header 'Accept: application/vnd.github+json' \
    --header "Authorization: Bearer ${GH_TOKEN}" \
    --header 'X-GitHub-Api-Version: 2022-11-28' \
    "${release_url}"
)"

case "${http_status}" in
  200)
    echo "exists=true" >> "${GITHUB_OUTPUT}"
    ;;
  404)
    echo "exists=false" >> "${GITHUB_OUTPUT}"
    ;;
  *)
    echo "Could not inspect GitHub Release ${RELEASE_TAG} (HTTP ${http_status})." >&2
    cat "${response_file}" >&2
    echo >&2
    exit 1
    ;;
esac
