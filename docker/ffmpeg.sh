#!/bin/sh

# 設定
OUTPUT_DIR="/videos"
YEAR=2

# YEAR年分のフォルダを作成
total_days=$((YEAR * 365))
i=0
while [ $i -lt $total_days ]; do
    future_date=$(date -d "+$i days" +%Y/%m/%d)
    mkdir -p "${OUTPUT_DIR}/${future_date}"
    i=$((i + 1))
done

# ffmpegの実行
ffmpeg \
    -i "${RTSP_URL}" \
    -c copy \
    -f segment \
    -segment_time "${SEGMENT_TIME}" \
    -reset_timestamps 1 \
    -movflags +faststart \
    -strftime 1 \
    /videos/%Y/%m/%d/%H%M%S.mp4
