#!/bin/sh

# 設定
OUTPUT_DIR="/videos"
YEAR=2

# 環境変数チェック
if [ -z "${RTSP_URL}" ]; then
    echo "ERROR: RTSP_URL is not set!"
    exit 1
fi

# Literal line breaks are invalid in a URL and would split log redaction records.
case "$RTSP_URL" in
    *"$(printf '\r')"*|*'
'*)
        echo "ERROR: RTSP_URL must not contain line breaks!" >&2
        exit 1
        ;;
esac

if [ -z "${SEGMENT_TIME}" ]; then
    echo "ERROR: SEGMENT_TIME is not set!"
    exit 1
fi

echo "=== Debug Information ==="
echo "RTSP_URL: [REDACTED]"
echo "SEGMENT_TIME: '${SEGMENT_TIME}'"
echo "OUTPUT_DIR: '${OUTPUT_DIR}'"
echo "YEAR: '${YEAR}'"
echo "=========================="

echo "Starting directory creation for ${YEAR} years..."

# YEAR年分のフォルダを作成
total_days=$((YEAR * 365))
echo "Total days to create: ${total_days}"

i=0
while [ $i -lt $total_days ]; do
    future_date=$(date -d "+$i days" +%Y/%m/%d)
    mkdir -p "${OUTPUT_DIR}/${future_date}"

    # 進捗表示（100日ごと）
    if [ $((i % 100)) -eq 0 ]; then
        echo "Progress: Created directories up to day $i (${future_date})"
    fi

    i=$((i + 1))
done

echo "Directory creation completed."

# ネットワーク接続確認
echo "Testing RTSP connection..."
if timeout 30 ffprobe -v error -timeout 5000000 -rtsp_transport tcp -show_entries format=duration "${RTSP_URL}" > /dev/null 2>&1; then
    echo "✅ RTSP connection successful"
else
    echo "❌ RTSP connection failed. Continuing anyway..."
fi

# FIFO keeps FFmpeg as the directly supervised child, without raw log files.
log_dir=$(mktemp -d) || exit 1
trap 'rm -rf "$log_dir"' 0
mkfifo "$log_dir/ffmpeg.log" || exit 1
# Pre-open both ends so a startup signal cannot strand a child in FIFO open().
exec 3<> "$log_dir/ffmpeg.log" || exit 1
exec 4< "$log_dir/ffmpeg.log" || exit 1
exec 5> "$log_dir/ffmpeg.log" || exit 1
exec 3>&-

filter_logs() {
    # Keep draining finalization diagnostics if the process group is signalled.
    trap '' TERM INT
    exec awk '
        BEGIN { url = ENVIRON["RTSP_URL"]; RS = "[\r\n]" }
        {
            line = $0
            redacted = ""
            while (url != "" && (at = index(line, url)) != 0) {
                redacted = redacted substr(line, 1, at - 1) "[REDACTED]"
                line = substr(line, at + length(url))
            }
            line = redacted line
            # Also hide rewritten/redirected URLs, including quotes in userinfo.
            gsub(/[[:alpha:]][[:alnum:]+.-]*:\/\/[^[:space:]]+/, "[REDACTED]", line)
            print line
            fflush()
        }
    '
}

finish_logs() {
    if [ -n "${log_pid:-}" ]; then
        wait "$log_pid"
    fi
}

# 信号ハンドリング
cleanup() {
    trap '' TERM INT
    echo "Received signal, gracefully shutting down FFmpeg..."
    recording_pid=${ffmpeg_pid:-}
    if [ -n "${recording_pid}" ]; then
        kill -TERM "${recording_pid}" 2>/dev/null || :
        wait "${recording_pid}" || :
    fi
    exec 4<&- 5>&-
    finish_logs || :
    exit 0
}

trap cleanup TERM INT

echo "Starting FFmpeg recording..."
echo "Command: ffmpeg -timeout 60 -rtsp_transport tcp -i [REDACTED] ..."

# RTSP AAC の key flag がない旧 FFmpeg でも音声を stream copy する。
# 非同期実行にして親シェルの trap から終了・MP4 確定を待つ。
# Defer shutdown until both children exist and the logger can drain FFmpeg.
shutdown_requested=false
trap 'shutdown_requested=true' TERM INT
ffmpeg \
    -timeout 60 \
    -rtsp_transport tcp \
    -i "${RTSP_URL}" \
    -avoid_negative_ts make_zero \
    -fflags +genpts+igndts \
    -c copy \
    -copyinkf:a \
    -f segment \
    -segment_time "${SEGMENT_TIME}" \
    -segment_format mp4 \
    -reset_timestamps 1 \
    -movflags +faststart \
    -strftime 1 \
    /videos/%Y/%m/%d/%H%M%S.mp4 >&5 2>&1 4<&- 5>&- &

ffmpeg_pid=$!
filter_logs <&4 >&2 4<&- 5>&- &
log_pid=$!
exec 4<&- 5>&-
trap cleanup TERM INT
if [ "$shutdown_requested" = true ]; then
    cleanup
fi
wait "$ffmpeg_pid"
recording_status=$?
if ! finish_logs; then
    echo "ERROR: FFmpeg log filtering failed." >&2
    [ "$recording_status" -ne 0 ] || recording_status=1
fi
exit "$recording_status"
