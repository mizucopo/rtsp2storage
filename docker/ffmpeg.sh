#!/bin/sh

OUTPUT_DIR="/videos"

LAST_FILE=$(ls -t "$OUTPUT_DIR"/output_*.mp4 2>/dev/null | head -n 1)

if [ -n "$LAST_FILE" ]; then
    LAST_NUMBER=$(echo "$LAST_FILE" | grep -oE '_[0-9]+\.')
    STRIPPED_NUMBER=$(echo "$LAST_NUMBER" | sed 's/^_0*//' | sed 's/\.//')
    [ -z "$STRIPPED_NUMBER" ] && STRIPPED_NUMBER=0
    NEXT_NUMBER=$((STRIPPED_NUMBER + 1))
else
    NEXT_NUMBER=0
fi

ffmpeg \
    -i ${RTSP_URL} \
    -c copy \
    -f segment \
    -segment_time ${SEGMENT_TIME} \
    -segment_wrap ${SEGMENT_WRAP} \
    -segment_start_number ${NEXT_NUMBER} \
    -reset_timestamps 1 \
    -movflags +faststart \
    /videos/output_%08d.mp4
