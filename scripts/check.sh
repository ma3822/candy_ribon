#!/usr/bin/env bash
# 在庫を 1 回確認する。cron / launchd から呼ばれる入口。
#
# 監視対象のサイトは国外・データセンターの IP を遮断しているため、
# このスクリプトは日本国内の回線につながった手元のマシンで動かす必要がある。
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

if [[ ! -x .venv/bin/python ]]; then
  echo "先に scripts/setup.sh を実行してください。" >&2
  exit 1
fi

mkdir -p logs
exec .venv/bin/python -m montbell_restock.cli check "$@" >> logs/check.log 2>&1
