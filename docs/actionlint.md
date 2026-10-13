# actionlint の導入と検証

## 対応状況

2026-10-13 UTC 時点で正式版の [actionlint v1.7.12](https://github.com/rhysd/actionlint/releases/tag/v1.7.12)
と [上流 main の `011a6d1`](https://github.com/rhysd/actionlint/tree/011a6d15e749bb3f2d771eed9c7aa0e7e3e10ee7)
は `concurrency.queue` 未対応。
この repository では、未マージの [上流 PR #654](https://github.com/rhysd/actionlint/pull/654) の
commit `644076a59742c2d1540ebd4686eab3c308f0e562` を暫定的に使用する。
正式リリースではないため、Homebrew の更新や `go install ...@latest` / `@main` では代替できない。

固定 commit は workflow と job の `queue: max` / `single` を受け入れ、
不正な queue 値、`queue: max` と静的な `cancel-in-progress: true` の併用を検出する。
GitHub の [concurrency の仕様](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
に従い、既存の `release-main`、`cancel-in-progress: false`、`queue: max` を保持する。
同じ group の実行は一つずつ進み、最大 100 件が待機できる。

## 導入

Git、Go 1.25.0 以上（上流の対応系列は 1.25 / 1.26）、ShellCheck を用意し、repository ルートで実行する。
GitHub と Go module 配布先へのネットワーク接続が必要。
ShellCheck は actionlint 内のシェル検査と、別途の品質コマンドの両方で使う。

```sh
bash .github/scripts/install-actionlint.sh
export PATH="$PWD/.tools/bin:$PATH"
hash -r
command -v actionlint
actionlint -version
go version -m .tools/bin/actionlint
actionlint
```

installer は上流から固定 SHA を直接取得して照合し、ソースを変更せずビルドする。
version 表示だけを `pr654-644076a59742c2d1540ebd4686eab3c308f0e562` に設定する。
取得・ビルドが失敗した場合は終了し、以前の binary を置き換えない。
生成物は Git 管理外の `.tools/bin/actionlint` に置き、グローバルの actionlint は変更しない。
新しいシェルでは上の PATH 設定と `hash -r` を再実行する。

`command -v` が `.tools/bin/actionlint` を指し、version と build 情報の `vcs.revision` が
固定 SHA と一致することを確認する。`vcs.modified=false` がソース未変更の証拠になる。
続く引数なしの `actionlint` は `.github/workflows` 全体を検査する。
workflow の加工、対象の除外、`-ignore`、`|| true` は使用しない。終了コード 0 の場合だけ成功とする。
追加の actionlint 設定ファイルは不要。

## 検証記録

2026-10-13 UTC、base `dec7f2b8d8736b822b205fd917128982fb240964` で実施。

| ツール・コマンド | 結果 |
| --- | --- |
| Homebrew actionlint 1.7.12 の `actionlint` | 終了コード 1。`docker-release.yml:15` の `queue` が未対応 |
| 上記 installer、Go 1.27.2 / darwin arm64 | 固定ソースからビルド成功 |
| `actionlint -version` | `pr654-644076a59742c2d1540ebd4686eab3c308f0e562` |
| `go version -m .tools/bin/actionlint` | `vcs.revision=644076a59742c2d1540ebd4686eab3c308f0e562`、`vcs.modified=false` |
| PATH 設定後の未加工 `actionlint` | 終了コード 0、診断なし、全 workflow を検査 |
| 固定ソースの `testdata/ok/concurrency_queue.yaml` を `actionlint -` に入力 | 終了コード 0。workflow / job の `max` と `single` を受理 |
| 固定ソースの `testdata/err/concurrency_queue.yaml` を `actionlint -` に入力 | 終了コード 1。不正値と `max` / `true` の併用を検出 |

## 正式版への切り替え

queue 対応を含む正式版が出たら、その version を固定して installer とこの手順を更新する。
全 workflow の未加工検査に加えて、不正な queue 値と `max` / `true` の併用が失敗することを確認する。
正式版への移行でも待機キューの設定と品質チェックは維持する。
