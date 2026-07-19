#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required.}"
: "${TAG_EXISTS:?TAG_EXISTS is required.}"
: "${RELEASE_EXISTS:?RELEASE_EXISTS is required.}"

version_image_exists="${VERSION_IMAGE_EXISTS:-}"
version_image_digest="${VERSION_IMAGE_DIGEST:-}"
latest_image_exists="${LATEST_IMAGE_EXISTS:-}"
latest_image_digest="${LATEST_IMAGE_DIGEST:-}"

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

if [[ ! "${version_image_exists}" =~ ^(true|false)$ ]]; then
  echo "VERSION_IMAGE_EXISTS must be true or false." >&2
  exit 1
fi

if [[ ! "${latest_image_exists}" =~ ^(true|false)$ ]]; then
  echo "LATEST_IMAGE_EXISTS must be true or false." >&2
  exit 1
fi

if [ "${version_image_exists}" = "true" ] && [ -z "${version_image_digest}" ]; then
  echo "VERSION_IMAGE_DIGEST is required when the version image exists." >&2
  exit 1
fi

if [ "${latest_image_exists}" = "true" ] && [ -z "${latest_image_digest}" ]; then
  echo "LATEST_IMAGE_DIGEST is required when the latest image exists." >&2
  exit 1
fi

if [ "${version_image_exists}" = "true" ] && [ "${TAG_EXISTS}" != "true" ]; then
  echo "Docker image exists without the matching git tag." >&2
  exit 1
fi

publish_version_image=false
repair_latest=false

if [ "${version_image_exists}" != "true" ]; then
  publish_version_image=true
elif [ "${latest_image_exists}" != "true" ] || [ "${latest_image_digest}" != "${version_image_digest}" ]; then
  repair_latest=true
fi

release_complete=false
if [ "${TAG_EXISTS}" = "true" ] \
  && [ "${RELEASE_EXISTS}" = "true" ] \
  && [ "${publish_version_image}" = "false" ] \
  && [ "${repair_latest}" = "false" ]; then
  release_complete=true
fi

{
  echo "release_complete=${release_complete}"
  if [ "${TAG_EXISTS}" = "true" ]; then
    echo "create_tag=false"
  else
    echo "create_tag=true"
  fi

  echo "publish_version_image=${publish_version_image}"
  echo "repair_latest=${repair_latest}"

  if [ "${RELEASE_EXISTS}" = "true" ]; then
    echo "create_release=false"
  else
    echo "create_release=true"
  fi
} >> "${GITHUB_OUTPUT}"
