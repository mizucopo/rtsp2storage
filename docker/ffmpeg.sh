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
    -timeout 60 \
    -rw_timeout 30000000 \
    -rtsp_transport tcp \
    -rtsp_flags prefer_tcp \
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
