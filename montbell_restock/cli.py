"""コマンドラインの入口。

    python -m montbell_restock.cli check     監視リストを確認し、再入荷なら通知する
    python -m montbell_restock.cli show URL  そのページの在庫表を一覧する
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import notify, state
from .fetch import FetchError, fetch
from .parse import extract_variants, find_variant

DEFAULT_WATCHLIST = Path("watchlist.json")
DEFAULT_STATE = Path("state/stock_state.json")

STATUS_LABEL = {
    state.IN_STOCK: "在庫あり",
    state.OUT_OF_STOCK: "在庫なし",
    state.UNKNOWN: "判定できず",
}


def load_watchlist(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("items", [])
    for item in items:
        missing = {"id", "name", "url", "color", "size"} - set(item)
        if missing:
            raise ValueError(f"{path} の項目に {sorted(missing)} がありません: {item}")
    return items


def evaluate(item: dict) -> tuple[str, str]:
    """1 件ぶんの在庫を調べ、(状態, 根拠) を返す。"""
    try:
        page = fetch(item["url"])
    except FetchError as exc:
        return state.UNKNOWN, f"ページを取得できませんでした: {exc}"

    variants = extract_variants(page.html)
    if not variants:
        return state.UNKNOWN, "在庫表を読み取れませんでした。ページ構造が変わった可能性があります"

    variant = find_variant(variants, color=item["color"], size=item["size"])
    if variant is None:
        available = ", ".join(sorted({f"{v.color}/{v.size}" for v in variants})[:20])
        return (
            state.UNKNOWN,
            f"{item['color']} / {item['size']} が見つかりませんでした。読めた組み合わせ: {available}",
        )

    if variant.in_stock is None:
        return state.UNKNOWN, f"在庫の表記を判定できませんでした: {variant.marker!r}"

    label = STATUS_LABEL[state.IN_STOCK if variant.in_stock else state.OUT_OF_STOCK]
    detail = f"{variant.color} / {variant.size} は {label}（表記: {variant.marker!r}）"
    return (state.IN_STOCK if variant.in_stock else state.OUT_OF_STOCK), detail


def _write_summary(lines: list[str]) -> None:
    print("\n".join(lines))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


def command_check(args: argparse.Namespace) -> int:
    items = load_watchlist(args.watchlist)
    store = state.Store.load(args.state)

    lines = ["## 在庫チェック結果", ""]
    unresolved = False

    for item in items:
        status, detail = evaluate(item)
        current, changed = store.record(item["id"], status=status, detail=detail)

        lines.append(f"- **{item['name']}**（{item['color']} / {item['size']}）: "
                     f"{STATUS_LABEL[status]}{'（変化あり）' if changed else ''}")
        lines.append(f"  - {detail}")

        if status == state.UNKNOWN:
            unresolved = True

        # 在庫ありに変わった最初の 1 回だけ知らせる。売り切れると通知済みは解除される。
        if status == state.IN_STOCK and not current.notified_at:
            message = notify.build_notification(
                name=item["name"],
                color=item["color"],
                size=item["size"],
                url=item["url"],
                detail=detail,
            )
            sent = notify.dispatch(message)
            store.mark_notified(item["id"])
            lines.append(f"  - 通知: {', '.join(sent) if sent else '送り先が未設定です'}")

    store.save()
    _write_summary(lines)

    # 判定できなかった項目があるなら、気づけるように失敗として終える。
    return 1 if unresolved else 0


def command_show(args: argparse.Namespace) -> int:
    try:
        page = fetch(args.url)
    except FetchError as exc:
        print(exc)
        return 1

    variants = extract_variants(page.html)
    if not variants:
        print("在庫表を読み取れませんでした")
        return 1

    for variant in variants:
        mark = {True: "在庫あり", False: "在庫なし", None: "不明"}[variant.in_stock]
        print(f"{variant.color:<28} {variant.size:<6} {mark:<8} {variant.marker!r}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="montbell_restock", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="監視リストを確認して通知する")
    check.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST)
    check.add_argument("--state", type=Path, default=DEFAULT_STATE)
    check.set_defaults(func=command_check)

    show = subparsers.add_parser("show", help="ページの在庫表を一覧する")
    show.add_argument("url")
    show.set_defaults(func=command_show)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
