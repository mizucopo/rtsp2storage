# Alpine FFmpeg 比較（Issue #30）

2026-10-13 に main `970a21aaf94bde29bebd517b8c23735099042328` の FFmpeg 7.1.1 と
Alpine 3.24 配布 FFmpeg 8.1.2 を比較した。初回の停止・AAC 問題を修正し、同じ修正版で
H.264/AAC・H.265/AAC の通常終了と Docker 停止を再比較した。全 30 MP4 が検証を通ったため、
**この検証範囲で配布版を採用し、本番 Dockerfile を 136 行から 16 行へ簡素化する。**
実カメラの制約・長時間録画の互換性は未確認で、Issue #30 の残件として扱う。

## 履歴・必要機能

[90858e4](https://github.com/mizucopo/rtsp2storage/commit/90858e48af64e6abc5276f79889366f3ff309f5c)
で Alpine 3.21 の APK からソースビルドへ変更している。
[PR #17](https://github.com/mizucopo/rtsp2storage/pull/17) の作者の本文・コメントに変更理由の記録はない。
bot の version・codec 制御という解釈は作者の要件として扱わない。直前の RTSP timeout・timestamp
調整との因果関係、対象カメラの制約も特定できなかった。

必要機能は RTSP/TCP、ffprobe、映像・音声の stream copy、segment/MP4、timestamp flags、strftime 名。
coreutils の date -d・timeout、Asia/Tokyo、/videos、RTSP_URL・SEGMENT_TIME と既定値は維持する。
録画では x264/x265 エンコード・字幕・フォントを直接使用しない。実行時ライブラリを APK に任せ、
ビルドツール・手動 COPY・依存列挙を削減する。Compose は prod/dev とも linux/amd64、workflow は
native build で multiarch 指定なし。今回も録画は linux/amd64 に限定し、arm64 の互換性は保証しない。

## 不具合の原因と修正

初回の既存スクリプトでは 7.1.1 が AAC を保存せず、両版が docker stop の 10 秒猶予後に exit 137、
最後の MP4 は moov atom not found だった。[初回結果 JSON](../tests/ffmpeg/results-2026-10-13.json) は
この失敗を示す 29 ファイルの記録である。

- 親シェルが foreground FFmpeg を待ち、停止 trap を実行できなかった。background 起動に変更し、
  子 PID だけへ TERM を送り、終了を wait してからシェルを終了する。通常の子の異常終了コードは維持する。
  TERM・INT 転送と終了待ちの回帰テストを追加した。
- 7.1.1 の [AAC RTP handler](https://github.com/FFmpeg/FFmpeg/blob/n7.1.1/libavformat/rtpdec_mpeg4.c#L335)
  には parser 指定がなく、8.1.2 の [handler](https://github.com/FFmpeg/FFmpeg/blob/n8.1.2/libavformat/rtpdec_mpeg4.c#L342)
  には AVSTREAM_PARSE_HEADERS がある。ライブ probe の AAC flags は ___ / K__ だった。
  7.1.1 の [stream copy 開始条件](https://github.com/FFmpeg/FFmpeg/blob/n7.1.1/fftools/ffmpeg_mux.c#L438)
  により全音声が捨てられていた。音声だけ `-copyinkf:a` を追加し、映像の keyframe 開始条件を維持する。
- AAC 欠落で interleave が待ち、終了時に分割がまとめて作られる。strftime は作成時刻なので同じ秒の
  パスを繰り返し開いていた。HEVC 切り分けでは未修正が AAC 819 入力→0 保存、映像 417 mux→217 現存、
  修正後は AAC 816→816、映像 417→417、全 5 MP4 の全 stream decode 成功だった。
  比較テストは同じ出力パスの再オープンも失敗として扱う。

timeout 60 秒、fflags の入力側への移動、interleave 上限 1 秒を個別に試しても AAC 欠落は直らなかった。
今回は既存 timeout・timestamp flags を維持する。`-timeout 60` は microseconds で、60 秒ではない。
既存値の見直し・断線時の運用設計は実運用条件を確認してから行う。

## 修正後の録画比較

Docker Desktop 29.8.2 / BuildKit 0.33.1、Apple arm64 ホスト、Docker VM 12 CPU / 約 8 GB。
録画イメージは両版とも linux/amd64、MediaMTX v1.21.2 は native arm64 で実行した。
固定 digest sha256:c7540465f868a02652118bea5a0daab12a29ac0f6cb8485abd535939ecddf886 は
amd64/arm64 を含む OCI index。サーバーの amd64 起動も確認済み。内部 network のみでポート公開なし。

320×180 / 25 fps / GOP 50 の H.264（B frame あり）、H.265 と 48 kHz stereo AAC の 12 秒 fixture を
配布版で生成し、ループして RTSP/TCP 配信した。各ケースの両コンテナは同じ配信・同じ修正版
/ffmpeg.sh・SEGMENT_TIME=4 を使う。両版の開始から 13 秒後に入力を終了するか、
両録画を docker stop --time 10 で停止した。

| 入力 / 終了方法 | 修正版 7.1.1 | 修正版 8.1.2 |
| --- | --- | --- |
| H.264 + AAC / 入力終了 | 3 MP4、exit 0、全て成功 | 3 MP4、exit 0、全て成功 |
| H.264 + AAC / Docker 停止 | 4 MP4、exit 0、全て成功 | 4 MP4、exit 0、全て成功 |
| H.265 + AAC / 入力終了 | 4 MP4、exit 0、全て成功 | 4 MP4、exit 0、全て成功 |
| H.265 + AAC / Docker 停止 | 4 MP4、exit 0、全て成功 | 4 MP4、exit 0、全て成功 |

候補版の同じ ffprobe で全 MP4 の必要 stream、全 packet の有限数値 DTS/PTS、stream 内の DTS 順序、
先頭映像 keyframe を確認した。ffmpeg -v error -xerror -map 0 -f null - の全 stream decode も全 30 個で成功。
これは decode 検証で、目視・聴取の再生確認ではない。終了前の配信・録画の稼働、exit 0、3 ファイル以上、
上書きなしも合否に含む。[修正後結果 JSON](../tests/ffmpeg/results-fixed-2026-10-13.json) に
packet 数・時刻・期間・image ID・ffmpeg -version 全出力・APK revision を残す。比較の終了値は 0 だった。

分割は keyframe と入力開始位置に依存し、4 秒指定でも一律 4 秒にはならない。今回の初回分割は
約 4.3〜7.8 秒、中間は約 2〜4 秒、末尾は約 0.8〜1.8 秒。両版の packet 数・時刻は完全一致しない。
負の timestamp は B frame と reset に伴い残るため、負値だけでは失敗とせず順序・decode を検証した。
両版とも最後まで必要 stream を保持し、同秒上書きのログはない。ファイル名・日付階層は JST を維持する。

## ビルド比較・品質チェック

初回比較で同じホスト・Alpine base・linux/amd64、--no-cache --load、同時ビルドなしで各 1 回測定した。
既存 base image を使い、初回 registry download は含まない。network・emulation の影響があり、
CI の予測値・統計的 benchmark ではない。サイズは初回 smoke 後の docker image inspect .Size。
録画スクリプト修正前の値だが、FFmpeg ビルド・APK インストール工程は今回採用する構成と同じ。
未変更の工程を重複測定せず、最終 Dockerfile のローカル build・起動を別途確認した。

| 項目 | 自前ビルド | 配布版 |
| --- | ---: | ---: |
| FFmpeg | 7.1.1 | 8.1.2（ffmpeg-8.1.2-r0） |
| build wall time | 252.785 秒 | 6.004 秒 |
| image Size | 151,811,736 bytes | 208,964,108 bytes |
| Dockerfile 行数 | 136 | 16（本番に採用） |

配布版は約 42 倍速くビルドでき、image は約 38% 大きかった。共有ライブラリを APK が管理するため、
依存列挙の削減は image 縮小を意味しない。最終 Dockerfile の build checks・ローカル build、
FFmpeg/ffprobe 起動、JST、ShellCheck、sh/bash 構文、Compose config、Python 回帰テスト・JSON parse、
diff check は成功した。actionlint 1.7.12 は既存 .github/workflows/docker-release.yml の
concurrency.queue: max が未対応で失敗する。他の診断はないが成功とは扱わず、チェックを緩めていない。

## 再実行

Python 3 と Docker / Buildx が必要。テスト用 tag と未作成の出力先を指定する。サーバーを pull し、
3 イメージの確認後に出力先を作成する。準備失敗では出力先を作らない。fixture・全 MP4・ログ・report.json を
残し、終了時に自分のコンテナ・network を削除する。過去のソース版 Dockerfile に最新の同じスクリプトを使う。

```sh
python3 -m unittest discover -s tests/recording -v
python3 -m unittest discover -s tests/ffmpeg -v
mkdir -p ../ffmpeg-comparison
git show 970a21aaf94bde29bebd517b8c23735099042328:Dockerfile > ../ffmpeg-comparison/source.Dockerfile
docker buildx build --platform linux/amd64 --load -f ../ffmpeg-comparison/source.Dockerfile -t rtsp2storage-compare-source:local .
docker buildx build --platform linux/amd64 --load -t rtsp2storage-compare-alpine:local .
python3 tests/ffmpeg/compare.py --baseline rtsp2storage-compare-source:local --candidate rtsp2storage-compare-alpine:local --server-image bluenviron/mediamtx@sha256:c7540465f868a02652118bea5a0daab12a29ac0f6cb8485abd535939ecddf886 --output ../ffmpeg-comparison/recordings
```

alpine:3.24 と APK は更新されるため、再実行時の image ID・version・結果も確認する。

## 実環境で残る確認

実カメラ、1 時間分割・長時間録画、断線・再接続、音声なし、AAC 以外の音声、arm64 の録画は未検証。
実カメラ比較には対象 codec/profile・GOP・音声・分割設定、再現条件、検証用入力または許可された RTSP 接続が必要。
認証情報の取得・設定・送信は行っていない。synthetic 比較を実運用全体の互換性とは扱わない。
元の移行理由・対象制約が判明した場合も Issue #30 で確認し、再現ケースを追加する。
