#!/bin/sh

# 設定
OUTPUT_DIR="/videos"
YEARS=10

# 日数を計算（年数 × 365 + うるう年補正）
DAYS=$(($YEARS * 365 + $YEARS / 4))

# ディレクトリの作成
start_date=$(date +%Y-%m-%d)
i=0
while [ $i -lt $DAYS ]; do
    folder_date=$(date -d "$start_date + $i days" +%Y/%m/%d 2>/dev/null || date -v+${i}d -j -f %Y-%m-%d $start_date +%Y/%m/%d)
    mkdir -p "$OUTPUT_DIR/$folder_date"
    i=$(($i + 1))
done

# ffmpegの実行
ffmpeg \
    -i ${RTSP_URL} \
    -c copy \
    -f segment \
    -segment_time ${SEGMENT_TIME} \
    -reset_timestamps 1 \
    -movflags +faststart \
    -strftime 1 \
    /videos/%Y/%m/%d/%H%M%S.mp4
