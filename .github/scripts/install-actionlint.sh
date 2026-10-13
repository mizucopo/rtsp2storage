#!/usr/bin/env bash
set -euo pipefail

# Upstream PR #654 is not released yet. Fetch its immutable source, not its
# moving branch or a release that cannot parse concurrency.queue.
revision=644076a59742c2d1540ebd4686eab3c308f0e562
repo_root="$(git rev-parse --show-toplevel)"
build_dir="$(mktemp -d)"
trap 'rm -rf "$build_dir"' EXIT

git init --quiet "$build_dir/source"
git -C "$build_dir/source" fetch --quiet --depth=1 \
  https://github.com/rhysd/actionlint.git "$revision"
git -C "$build_dir/source" checkout --quiet --detach "$revision"
test "$(git -C "$build_dir/source" rev-parse HEAD)" = "$revision"

(
  cd "$build_dir/source"
  go build -trimpath \
    -ldflags "-X github.com/rhysd/actionlint.version=pr654-$revision" \
    -o "$build_dir/actionlint" ./cmd/actionlint
)

mkdir -p "$repo_root/.tools/bin"
mv "$build_dir/actionlint" "$repo_root/.tools/bin/actionlint"
"$repo_root/.tools/bin/actionlint" -version
