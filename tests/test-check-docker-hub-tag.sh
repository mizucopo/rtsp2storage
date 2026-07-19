#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
checker="${repo_root}/scripts/check-docker-hub-tag.sh"
test_root="$(mktemp -d)"
trap 'rm -rf "${test_root}"' EXIT

mkdir -p "${test_root}/bin"
cat > "${test_root}/bin/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

output_file=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--output" ]; then
    output_file="$2"
    shift 2
  else
    shift
  fi
done

printf '%s' "${FAKE_RESPONSE_BODY:-}" > "${output_file}"
printf '%s' "${FAKE_HTTP_STATUS}"
EOF
chmod +x "${test_root}/bin/curl"

run_checker() {
  local work_dir="$1"
  local http_status="$2"
  local response_body="${3:-}"

  mkdir -p "${work_dir}"
  PATH="${test_root}/bin:${PATH}" \
    FAKE_HTTP_STATUS="${http_status}" \
    FAKE_RESPONSE_BODY="${response_body}" \
    GITHUB_OUTPUT="${work_dir}/github-output" \
    IMAGE="mizucopo/rtsp2storage:v1.2.2" \
    RUNNER_TEMP="${work_dir}" \
    "${checker}"
}

work_dir="${test_root}/existing-tag"
run_checker "${work_dir}" 200 '{"digest":"sha256:abc123"}'
grep -Fx 'exists=true' "${work_dir}/github-output" >/dev/null
grep -Fx 'digest=sha256:abc123' "${work_dir}/github-output" >/dev/null
echo "ok: existing Docker Hub tag returns its digest"

work_dir="${test_root}/missing-tag"
run_checker "${work_dir}" 404
grep -Fx 'exists=false' "${work_dir}/github-output" >/dev/null
grep -Fx 'digest=' "${work_dir}/github-output" >/dev/null
echo "ok: missing Docker Hub tag is detected"

work_dir="${test_root}/missing-digest"
mkdir -p "${work_dir}"
if run_checker "${work_dir}" 200 '{}' 2> "${work_dir}/error"; then
  echo "Docker Hub response without a digest was accepted" >&2
  exit 1
fi
grep -Fx 'Docker Hub tag response did not include a digest: mizucopo/rtsp2storage:v1.2.2' "${work_dir}/error" >/dev/null
echo "ok: existing Docker Hub tag requires a digest"

work_dir="${test_root}/lookup-error"
mkdir -p "${work_dir}"
if run_checker "${work_dir}" 500 '{"message":"server error"}' 2> "${work_dir}/error"; then
  echo "Docker Hub lookup error was accepted" >&2
  exit 1
fi
grep -Fx 'Could not inspect Docker Hub tag: mizucopo/rtsp2storage:v1.2.2 (HTTP 500)' "${work_dir}/error" >/dev/null
echo "ok: Docker Hub lookup errors fail closed"
