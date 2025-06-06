# RTSP To Storage

RTSP で公開されているライブ配信をファイル化します。

## 利用方法

1. docker image を pull する

```sh
docker pull mizucopo/rtsp2storage:latest
```

2. docker コンテナを立ち上げる

```sh
docker run --rm -d \
  -v $(pwd)/videos:/videos \
  -e RTSP_URL="rtsp://example.com/live0" \
  # Note: The default segment time in the image is 60 seconds.
  # The example below overrides it to 3600 seconds (1 hour) for longer segments.
  -e SEGMENT_TIME=3600 \
  mizucopo/rtsp2storage:latest
```

## 開発手順

1. docker image のビルドを行います

```sh
docker compose build prod
docker compose build dev
```

2. docker コンテナを立ち上げます

```sh
docker run --rm -it \
  -v $(pwd)/videos:/videos \
  -e RTSP_URL="rtsp://example.com/live0" \
  -e SEGMENT_TIME=3600 \
  mizucopo/rtsp2storage:develop \
  /bin/sh
```

3. 諸々確認します
4. ビルドテストを実行します

```sh
act -j build-and-push
```

5. GitHub へプルリクエストを行います

## Contact

質問等は X まで ([@mizu_copo](https://twitter.com/mizu_copo)).

## License

This project is published under the MIT License. For more details, please refer to the [LICENSE file](/LICENSE).
