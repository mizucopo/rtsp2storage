# Alpine FFmpeg 比較（Issue #30）

2026-10-13 に main `76ce7b1c3ecc1d41be579c923001cc29028855b4` の
FFmpeg 7.1.1 と Alpine 3.24 配布 FFmpeg 8.1.2 を比較した。
**停止時の MP4 確定と録画結果の同等性を確認できなかったため、本番 Dockerfile は維持する。**
候補は `tests/ffmpeg/Dockerfile.alpine` に置き、録画スクリプトは変更しない。

## 履歴・必要機能

[90858e4](https://github.com/mizucopo/rtsp2storage/commit/90858e48af64e6abc5276f79889366f3ff309f5c)
で Alpine 3.21 の `apk add ffmpeg` をソースビルドへ変更している。
[PR #17](https://github.com/mizucopo/rtsp2storage/pull/17) の作者の本文・コメントに
変更理由の記録はない。bot の「version・codec 機能の制御」という解釈は、作者の要件として扱わない。
直前の履歴には RTSP timeout と timestamp flags の調整があるが、変更との因果関係は不明。
実運用のカメラ、codec、障害の再現条件もリポジトリからは特定できなかった。

現行の `docker/ffmpeg.sh` が必要とするのは RTSP/TCP 入力、`ffprobe`、映像・音声の
stream copy、segment/MP4 muxer、既存 timestamp flags、strftime のファイル名である。
`coreutils` の `date -d` と `timeout`、Asia/Tokyo、`/videos`、既存環境変数も維持する。
x264/x265 のエンコード・字幕・フォント機能は録画コマンドで直接使用しない。
Compose は prod/dev とも `linux/amd64` を指定する。品質・公開 workflow は native build で、
multiarch 指定はない。この比較も `linux/amd64` に限定し、arm64 対応を保証しない。

## 条件と結果

Docker Desktop 29.8.2 / BuildKit 0.33.1、Apple arm64 ホスト、Docker VM 12 CPU / 約 8 GB。
両録画イメージを同じ `linux/amd64` 条件で実行した。RTSP サーバーは
[MediaMTX](https://mediamtx.org/docs/references/configuration-file) v1.21.2（arm64）、
digest `sha256:c7540465f868a02652118bea5a0daab12a29ac0f6cb8485abd535939ecddf886`。
この digest は OCI image index で、linux/amd64 と linux/arm64 の manifest を含む。
JSON の server `arm64` は測定ホストで選択された実体を表す。再実行時のサーバーはホストの native platform を使い、
amd64 ホストでは index 内の amd64 image を利用できる（amd64 での起動も別途確認済み）。
Docker の内部 network のみ使用し、ホストへポートを公開していない。

候補 FFmpeg で 320×180 / 25 fps / GOP 50 の H.264、H.265 と 48 kHz stereo AAC の
12 秒 fixture を生成した。H.264 は B frame を含む。fixture をループして RTSP/TCP で配信し、
各ケースの両録画コンテナを同じ配信に接続した。
`SEGMENT_TIME=4` とし、各イメージ内の既存 `/ffmpeg.sh` をそのまま実行した。
両コンテナが録画を開始してから 13 秒後に、入力を終了するか、両録画コンテナを
同じ `docker stop --time 10` で停止した。

全 MP4 を候補の同一 `ffprobe` で調べ、映像・音声 packet、DTS の順序、先頭映像 keyframe を記録し、
`ffmpeg -xerror -map 0 -f null -` で全 stream を decode した。
この「再生確認」は decode 検証であり、目視・聴取による確認ではない。
ファイル名は両版とも Asia/Tokyo の日付階層になった。

| 入力 / 終了方法 | 現行 7.1.1 | 候補 8.1.2 |
| --- | --- | --- |
| H.264 + AAC / 入力終了 | MP4 2 個、映像のみ。exit 0 | MP4 4 個、全て映像・音声 decode 成功。exit 0 |
| H.265 + AAC / 入力終了 | MP4 2 個、映像のみ。exit 0 | MP4 3 個、全て映像・音声 decode 成功。exit 0 |
| H.264 + AAC / docker stop | MP4 3 個、最後は `moov atom not found`。exit 137 | MP4 6 個、最後は同エラー。exit 137 |
| H.265 + AAC / docker stop | MP4 3 個、最後は `moov atom not found`。exit 137 | MP4 6 個、最後は同エラー。exit 137 |

確定済み MP4 の映像は全て decode 成功し、各 stream 内の DTS は単調だった。
最終再実行の候補の通常録画では最初の分割が約 7.7 / 5.7 秒、中間が約 2 / 4 秒、最後が約 0.3 / 3.9 秒だった。
GOP・開始位置・既存 timestamp 処理により、4 秒指定でも各 MP4 の長さは一律 4 秒にはならない。
候補の後続ファイルには映像 DTS 約 -0.08 / -0.12 秒、AAC PTS 約 -0.06〜-0.12 秒もある。
負値の有無だけで正常とは判定せず、packet 順序と decode を確認した。
全 4 ケースを再実行しても AAC・停止時 MP4 の結論は同じだったが、開始位置により分割数・長さは変わった。
JSON と表は、終了前の稼働状態と終了コードも合否に含めた最終再実行の 29 ファイルを示す。

現行の RTSP 入力ログには AAC stream と copy mapping があるが、出力ログは `audio:0KiB` で、
MP4 に音声 stream がない。同じ秒の出力名を繰り返し開くログもあり、分割数が候補と異なる。
原因は未確定であり、全てのカメラで発生する問題と一般化しない。
停止時は両版とも 10 秒の猶予後に強制終了し、trap の `Received signal` ログは現れなかった。
shell が foreground FFmpeg の終了を待つことが原因と推測されるが、停止処理の修正検証は未実施。
現在の trap は今回の条件でファイルを確定する動作にならなかった。
本 PR では timeout・signal・timestamp 処理の修正まで範囲を広げない。

## ビルド比較

同じホスト・platform・Alpine base、`--no-cache --load`、同時ビルドなしで各 1 回測定した。
既存 base image は利用し、registry の初回 download は含まない。ネットワーク・emulation の影響があり、
CI の予測値や統計的な benchmark ではない。サイズは smoke 実行後の `docker image inspect .Size`。

| 項目 | 現行 | 配布版候補 |
| --- | ---: | ---: |
| FFmpeg | 7.1.1 自前ビルド | 8.1.2（Alpine `ffmpeg`） |
| build wall time | 252.785 秒 | 6.004 秒 |
| image Size | 151,811,736 bytes | 208,964,108 bytes |
| Dockerfile 行数 | 136 | 16（候補のみ。本番変更 0 行） |

候補は約 42 倍速くビルドできたが、image は約 38% 大きくなった。
配布版は追加の共有ライブラリを APK が管理するため、手動列挙の削減は image 縮小を意味しない。
両版の `ffmpeg` / `ffprobe` 起動、JST、Docker build checks は成功した。
既存の ShellCheck・sh/bash 構文・Compose config・diff check も成功。
`actionlint 1.7.12` は既存の `.github/workflows/docker-release.yml` の
`concurrency.queue: max` を未対応として失敗した。他の診断はないが、成功とは扱わない。

## 再実行

Python 3 と Docker / Buildx が必要。既存イメージを上書きしないテスト用 tag を使う。
比較開始時にサーバーイメージを pull し、3 イメージの確認が成功してから出力 directory を作成する。
この準備段階が失敗しても出力先を作らないため、同じコマンドで再試行できる。
出力先は未作成の directory を指定する。fixture、MP4、ログ、packet の要約を含む
`report.json` を残し、テスト用コンテナと network は終了時に削除する。
全ケースで終了要求前に配信と両録画コンテナが稼働し、両版が exit 0 で終了し、
3 個以上の MP4 に必要な映像・音声があり、先頭 keyframe・DTS 順序・decode が
成功した場合のみテストは exit 0。今回の結果では exit 1 が正しい。

```sh
python3 -m unittest discover -s tests/ffmpeg -v
mkdir -p ../ffmpeg-comparison
git show 76ce7b1c3ecc1d41be579c923001cc29028855b4:Dockerfile > ../ffmpeg-comparison/baseline.Dockerfile
docker buildx build --platform linux/amd64 --no-cache --load \
  -f ../ffmpeg-comparison/baseline.Dockerfile -t rtsp2storage-compare-baseline:local .
docker buildx build --platform linux/amd64 --no-cache --load \
  -f tests/ffmpeg/Dockerfile.alpine -t rtsp2storage-compare-alpine:local .
python3 tests/ffmpeg/compare.py \
  --baseline rtsp2storage-compare-baseline:local \
  --candidate rtsp2storage-compare-alpine:local \
  --server-image bluenviron/mediamtx@sha256:c7540465f868a02652118bea5a0daab12a29ac0f6cb8485abd535939ecddf886 \
  --output ../ffmpeg-comparison/recordings
```

`alpine:3.24` と APK の配布内容は更新されるため、再実行時は image ID・package version・結果も記録する。
今回の packet 要約は [比較結果 JSON](../tests/ffmpeg/results-2026-10-13.json) に残す。

## 移行条件・未検証

[Issue #30](https://github.com/mizucopo/rtsp2storage/issues/30) で次を追跡する。

- 停止時に FFmpeg を終了・wait し、最後の MP4 まで decode できることを両版で確認する。
- 現行で AAC と分割結果が異なる原因を切り分け、実運用の codec・録画設定で差が許容されるか確認する。
- 同じ実運用 RTSP 入力で映像・音声、分割境界、timestamp、通常録画・停止時再生を確認する。
- 1 時間分割・長時間録画、ネットワーク断・再接続、音声なし、AAC 以外の音声は未検証。
- 元の移行理由や対象カメラの制約が判明した場合、その再現ケースを追加する。

これらの条件を満たした時点で本番 Dockerfile のソースビルド・手動依存列挙を削減する。
今回の synthetic RTSP 比較だけで実運用全体の互換性を確認済みとは扱わない。
