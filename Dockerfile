FROM alpine:3.24

RUN apk add --no-cache coreutils ffmpeg tzdata \
    && cp /usr/share/zoneinfo/Asia/Tokyo /etc/localtime \
    && echo "Asia/Tokyo" > /etc/timezone \
    && apk del tzdata

COPY docker/ffmpeg.sh /ffmpeg.sh
RUN chmod +x /ffmpeg.sh

WORKDIR /videos

ENV RTSP_URL=rtsp://example.com/live \
    SEGMENT_TIME=3600

CMD ["/bin/sh", "/ffmpeg.sh"]
