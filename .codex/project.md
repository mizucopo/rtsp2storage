# rtsp2storage

- Preserve the FFmpeg source build, recording script, Asia/Tokyo timezone, and
  Docker Compose services during template updates.
- The root Docker build context permits only `Dockerfile` and
  `docker/ffmpeg.sh`. Keep `docker/**` excluded before allowing the entrypoint.
- Release workflows accept `DOCKER_TOKEN` as the existing fallback for
  `DOCKERHUB_TOKEN`; do not change repository secrets during a template update.
- Run `actionlint`, `shellcheck docker/ffmpeg.sh .github/scripts/*.sh`,
  `sh -n docker/ffmpeg.sh`, `bash -n .github/scripts/*.sh`,
  `docker compose config --quiet`, and `git diff --check`.
- Verify Docker builds with `docker buildx build --check .`, then a local image
  build and `ffmpeg -version` smoke test. Never push an image as verification.
