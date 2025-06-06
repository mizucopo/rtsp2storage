#!/bin/sh

# 設定
OUTPUT_DIR="/videos"
YEARS=10

# 日数を計算（年数 × 365 + うるう年補正）
DAYS=$((YEARS * 365 + YEARS / 4))

# ディレクトリの作成
# BusyBox など環境差異を考慮し、エポック秒を基準に計算する
start_date=$(date +%Y-%m-%d)
start_sec=$(date -d "$start_date" +%s 2>/dev/null || date -j -f %Y-%m-%d "$start_date" +%s)
i=0
while [ "$i" -lt "$DAYS" ]; do
    current_sec=$((start_sec + i * 86400))
    folder_date=$(date -u -d "@$current_sec" +%Y/%m/%d 2>/dev/null || date -u -r "$current_sec" +%Y/%m/%d)
    mkdir -p "$OUTPUT_DIR/$folder_date"
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
