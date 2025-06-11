#!/bin/sh

# 設定
OUTPUT_DIR="/videos"
YEAR=2

# 環境変数チェック
if [ -z "${RTSP_URL}" ]; then
    echo "ERROR: RTSP_URL is not set!"
    exit 1
fi

if [ -z "${SEGMENT_TIME}" ]; then
    echo "ERROR: SEGMENT_TIME is not set!"
    exit 1
fi

echo "=== Debug Information ==="
echo "RTSP_URL: '${RTSP_URL}'"
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
timeout 30 ffprobe -v error -timeout 5000000 -rtsp_transport tcp -show_entries format=duration "${RTSP_URL}" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ RTSP connection successful"
else
    echo "❌ RTSP connection failed. Continuing anyway..."
fi

# 信号ハンドリング
cleanup() {
    echo "Received signal, gracefully shutting down FFmpeg..."
    pkill -TERM ffmpeg
    exit 0
}

trap cleanup TERM INT

echo "Starting FFmpeg recording..."
echo "Command: ffmpeg -timeout 60 -rtsp_transport tcp -i '${RTSP_URL}' ..."

# ffmpegの実行
ffmpeg \
    -timeout 60 \
    -rtsp_transport tcp \
    -i "${RTSP_URL}" \
    -avoid_negative_ts make_zero \
    -fflags +genpts+igndts \
    -c copy \
    -f segment \
    -segment_time "${SEGMENT_TIME}" \
    -segment_format mp4 \
    -reset_timestamps 1 \
    -movflags +faststart \
    -strftime 1 \
    /videos/%Y/%m/%d/%H%M%S.mp4
