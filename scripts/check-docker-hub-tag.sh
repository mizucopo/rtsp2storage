#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required.}"
: "${IMAGE:?IMAGE is required.}"

response_file="$(mktemp "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/docker-hub-tag-response.XXXXXX")"
trap 'rm -f "${response_file}"' EXIT

repository_path="${IMAGE%:*}"
namespace="${repository_path%%/*}"
repository="${repository_path#*/}"
tag="${IMAGE##*:}"
tag_url="https://hub.docker.com/v2/namespaces/${namespace}/repositories/${repository}/tags/${tag}"
http_status="$(
  curl \
    --silent \
    --show-error \
    --output "${response_file}" \
    --write-out '%{http_code}' \
    "${tag_url}"
)"

case "${http_status}" in
  200)
    if ! digest="$(jq -er '.digest | select(type == "string" and length > 0)' "${response_file}" 2>/dev/null)"; then
      echo "Docker Hub tag response did not include a digest: ${IMAGE}" >&2
      exit 1
    fi
    {
      echo "exists=true"
      echo "digest=${digest}"
    } >> "${GITHUB_OUTPUT}"
    ;;
  404)
    {
      echo "exists=false"
      echo "digest="
    } >> "${GITHUB_OUTPUT}"
    ;;
  *)
    echo "Could not inspect Docker Hub tag: ${IMAGE} (HTTP ${http_status})" >&2
    cat "${response_file}" >&2
    echo >&2
    exit 1
    ;;
esac
