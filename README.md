# rtsp2storage

RTSP ストリームを一定時間ごとの MP4 ファイルとして保存する Docker イメージです。
映像と音声は再エンコードせずに保存します。

## 必要なもの

- Docker
- 接続可能な RTSP ストリームの URL

## 使い方

保存先のディレクトリを作成します。

```sh
mkdir -p videos
```

コンテナを起動します。`RTSP_URL` は使用するストリームの URL に置き換えてください。

```sh
docker run --rm -d \
  --name rtsp2storage \
  -v "$(pwd)/videos:/videos" \
  -e RTSP_URL="rtsp://example.com/live" \
  -e SEGMENT_TIME="3600" \
  mizucopo/rtsp2storage:latest
```

録画状況はコンテナのログで確認できます。

```sh
docker logs -f rtsp2storage
```

録画を停止するには、コンテナを停止します。

```sh
docker stop rtsp2storage
```

## 設定

| 環境変数 | 説明 | 既定値 |
| --- | --- | --- |
| `RTSP_URL` | 録画する RTSP ストリームの URL | `rtsp://example.com/live` |
| `SEGMENT_TIME` | 1 ファイルあたりの録画時間（秒） | `3600` |

イメージ内の `RTSP_URL` はサンプル値のため、実際の URL を必ず指定してください。

## 出力

録画ファイルは、コンテナのタイムゾーン（Asia/Tokyo）を基準に次の形式で保存されます。

```text
videos/YYYY/MM/DD/HHMMSS.mp4
```

たとえば、2026 年 7 月 18 日 10 時 30 分に開始したファイルは
`videos/2026/07/18/103000.mp4` に保存されます。

## ソースからビルドする

本番用イメージをビルドします。

```sh
docker compose build prod
```

ビルド後は、[使い方](#使い方)と同じコマンドでローカルイメージを実行できます。

開発用イメージでは、組み込まれている FFmpeg のバージョンを確認できます。

```sh
docker compose build dev
docker compose run --rm dev
```

## ライセンス

このプロジェクトは [MIT License](LICENSE) のもとで公開されています。
