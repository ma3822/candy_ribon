# モンベル 再入荷リマインダー

モンベル ウェブショップの商品ページを定期的に見て、指定した「カラー × サイズ」が
在庫なしから在庫ありに変わったときに通知する。

最初の監視対象は **US プラズマ1000 アルパインダウン パーカ の LGY / XL**。

## 先に知っておくこと

**手元のマシンで動かす必要がある。GitHub Actions のホストランナーでは動かない。**

montbell 側が国外・データセンターの IP からの接続を落としている。GitHub の
ホストランナー（米国 Azure）から確認したところ、DNS は正常に引けるのに
443 と 80 のどちらも接続タイムアウトになった。拒否応答すら返ってこない。
`.github/workflows/netcheck.yml` に実測結果を残してある。

そのため、日本国内の回線につながったマシン（ふだん使っている PC / Mac）で
定期実行する形にしてある。

## 使いかた

```sh
git clone https://github.com/ma3822/candy_ribon.git
cd candy_ribon
./scripts/setup.sh
```

`setup.sh` は次のことをする。

1. `.venv` を作って依存関係を入れる
2. 実際に商品ページを読めるか 1 回試す
3. macOS なら launchd に 30 分おきの実行を登録する（Linux なら cron の行を表示する）

在庫ありに変わると、デスクトップ通知が出る。ログは `logs/check.log` に貯まる。

登録を解除するには:

```sh
launchctl unload ~/Library/LaunchAgents/jp.montbell.restock.plist
rm ~/Library/LaunchAgents/jp.montbell.restock.plist
```

## 動作確認していないところ

**在庫表の読み取りは、実際の商品ページに当てて検証できていない。**

このリポジトリを作った環境からも GitHub のランナーからも montbell に到達できず、
生の HTML を一度も取得できなかった。パーサはモンベルのページで一般的な
「カラーを行、サイズを列に取った表」と「カラー / サイズ を 1 つの option に
まとめた select」の両方を読める作りにしてあり、その範囲ではテストが通っている
（`tests/`）。ただし実物と噛み合うかは未確認。

最初に `scripts/setup.sh` を走らせたとき、手順 2 で読めなければそこで止まる。
そのときは次のコマンドで実際の構造を確認できる。

```sh
# 読み取れた「カラー × サイズ」の一覧を出す
.venv/bin/python -m montbell_restock.cli show \
  "https://webshop.montbell.jp/goods/disp.php?product_id=2301257"

# 生の HTML の構造をそのまま吐き出す
.venv/bin/python -m montbell_restock.diagnose \
  "https://webshop.montbell.jp/goods/disp.php?product_id=2301257"
```

`diagnose` の出力を渡してもらえれば、パーサを実物に合わせて直せる。

なお、商品ページに montbell 公式の入荷お知らせメールがあるなら、そちらのほうが
確実。ページを確認できていないので、あるかどうかは分かっていない。

## 通知の送り先

使える送り先すべてに送る。どれも設定が無ければ何も送らない。

| 送り先 | 有効になる条件 |
| --- | --- |
| デスクトップ通知 | 手元のマシンで実行したとき（macOS / Linux） |
| GitHub Issue | `GITHUB_TOKEN` と `GITHUB_REPOSITORY` があるとき |
| Slack / Discord | `RESTOCK_WEBHOOK_URL` を設定したとき |

通知は「在庫なし → 在庫あり」に変わった 1 回だけ出る。在庫ありが続いている間は
繰り返さない。一度売り切れてまた入荷したら、また通知する。

## 監視対象を増やす

`watchlist.json` に足す。`id` は状態の記録に使う名前なので、重複しなければ何でもよい。

```json
{
  "items": [
    {
      "id": "plasma1000-alpine-down-parka-lgy-xl",
      "name": "US プラズマ1000 アルパインダウン パーカ",
      "url": "https://webshop.montbell.jp/goods/disp.php?product_id=2301257",
      "color": "LGY",
      "size": "XL"
    }
  ]
}
```

`color` は色コード（`LGY`）でも表示名でも当たる。`size` は完全一致で見るので、
`XL` が `XXL` に当たることはない。

## 中身

| ファイル | 役割 |
| --- | --- |
| `montbell_restock/fetch.py` | ページの取得と文字コードの判定 |
| `montbell_restock/parse.py` | 在庫表から「カラー × サイズ」ごとの在庫を読む |
| `montbell_restock/state.py` | 前回の状態の記録。変化した瞬間だけ通知するために使う |
| `montbell_restock/notify.py` | 通知の送出 |
| `montbell_restock/cli.py` | `check` と `show` の入口 |
| `montbell_restock/diagnose.py` | ページ構造の調査用 |

状態は `state/stock_state.json` に残る。チェックのたびに書き換わらないよう、
最終チェックは日付までしか持たせていない。

テスト:

```sh
.venv/bin/python -m pytest tests/ -q
```

## セルフホストランナーで動かす場合

手元のマシンを GitHub のセルフホストランナーとして登録すれば、GitHub Actions の
スケジュールでも動かせる。その場合は `.github/workflows/restock-check.yml` の
`schedule` のコメントを外す。launchd / cron で足りるなら、そちらのほうが簡単。
