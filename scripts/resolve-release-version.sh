#!/usr/bin/env bash
set -euo pipefail

version_raw="$(cat version)"

case "${version_raw}" in
  *$'\n'*)
    echo "version must contain exactly one line." >&2
    exit 1
    ;;
esac

version="$(printf '%s' "${version_raw}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

if [ -z "${version}" ]; then
  echo "version must not be empty." >&2
  exit 1
fi

if [[ ! "${version}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "version contains characters that are not valid for this release tag." >&2
  exit 1
fi

{
  echo "version=${version}"
  echo "release_tag=${version}"
  echo "image=${IMAGE_REPOSITORY}:${version}"
} >> "${GITHUB_OUTPUT}"
