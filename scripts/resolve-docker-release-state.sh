#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required.}"
: "${TAG_EXISTS:?TAG_EXISTS is required.}"
: "${RELEASE_EXISTS:?RELEASE_EXISTS is required.}"

image_exists="${IMAGE_EXISTS:-}"

if [[ ! "${TAG_EXISTS}" =~ ^(true|false)$ ]]; then
  echo "TAG_EXISTS must be true or false." >&2
  exit 1
fi

if [[ ! "${RELEASE_EXISTS}" =~ ^(true|false)$ ]]; then
  echo "RELEASE_EXISTS must be true or false." >&2
  exit 1
fi

if [ "${RELEASE_EXISTS}" = "true" ] && [ "${TAG_EXISTS}" != "true" ]; then
  echo "GitHub Release exists without the matching git tag." >&2
  exit 1
fi

if [ "${TAG_EXISTS}" = "true" ] && [ "${RELEASE_EXISTS}" = "true" ]; then
  {
    echo "release_complete=true"
    echo "create_tag=false"
    echo "publish_image=false"
    echo "create_release=false"
  } >> "${GITHUB_OUTPUT}"
  exit 0
fi

if [[ ! "${image_exists}" =~ ^(true|false)$ ]]; then
  echo "IMAGE_EXISTS must be true or false for an incomplete release." >&2
  exit 1
fi

if [ "${image_exists}" = "true" ] && [ "${TAG_EXISTS}" != "true" ]; then
  echo "Docker image exists without the matching git tag." >&2
  exit 1
fi

{
  echo "release_complete=false"
  if [ "${TAG_EXISTS}" = "true" ]; then
    echo "create_tag=false"
  else
    echo "create_tag=true"
  fi

  if [ "${image_exists}" = "true" ]; then
    echo "publish_image=false"
  else
    echo "publish_image=true"
  fi

  echo "create_release=true"
} >> "${GITHUB_OUTPUT}"
