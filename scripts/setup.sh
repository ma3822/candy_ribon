#!/usr/bin/env bash
# 依存関係を入れ、30 分おきの定期実行を登録する。
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

echo "==> 仮想環境を用意します"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

echo "==> 商品ページを読めるか確認します"
if ! .venv/bin/python -m montbell_restock.cli check; then
  cat >&2 <<'MESSAGE'

在庫を判定できませんでした。上の出力を確認してください。
ページ構造が変わっている場合は、次のコマンドで生の HTML を確認できます。

  .venv/bin/python -m montbell_restock.diagnose \
    "https://webshop.montbell.jp/goods/disp.php?product_id=2301257"

MESSAGE
  exit 1
fi

label="jp.montbell.restock"
plist="${HOME}/Library/LaunchAgents/${label}.plist"

if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "==> launchd に 30 分おきの実行を登録します"
  mkdir -p "${HOME}/Library/LaunchAgents"
  cat > "${plist}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${repo_root}/scripts/check.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>1800</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>${repo_root}/logs/launchd.err.log</string>
</dict>
</plist>
PLIST

  launchctl unload "${plist}" 2>/dev/null || true
  launchctl load "${plist}"
  echo "登録しました: ${plist}"
  echo "解除するには: launchctl unload ${plist} && rm ${plist}"
else
  echo "==> crontab に次の行を追加してください（crontab -e）"
  echo "*/30 * * * * ${repo_root}/scripts/check.sh"
fi

echo
echo "ログは ${repo_root}/logs/check.log に追記されます。"
