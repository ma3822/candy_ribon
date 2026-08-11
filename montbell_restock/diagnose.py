"""商品ページの構造を実測してログに吐き出すための調査用コマンド。

在庫表記の持ち方（HTML の表なのか、JS 埋め込みの JSON なのか）は
実際のページを見ないと分からない。パーサを書く前・壊れたときに
これを走らせて、生の構造を確認するために使う。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from .fetch import fetch

# 在庫まわりで使われがちな語。script タグを絞り込むのに使う。
STOCK_HINTS = (
    "stock",
    "zaiko",
    "在庫",
    "goods",
    "sku",
    "size",
    "color",
    "カート",
    "入荷",
)


def _rule(title: str) -> None:
    print(f"\n{'=' * 70}\n== {title}\n{'=' * 70}")


def _dump_context(html: str, needle: str, *, window: int, limit: int) -> None:
    positions = [m.start() for m in re.finditer(re.escape(needle), html)]
    print(f"'{needle}' の出現回数: {len(positions)}")
    for index, position in enumerate(positions[:limit], start=1):
        start = max(0, position - window)
        end = min(len(html), position + window)
        excerpt = html[start:end].replace("\n", " ")
        excerpt = re.sub(r"\s{2,}", " ", excerpt)
        print(f"\n--- 出現 {index}/{len(positions)} (offset {position}) ---")
        print(excerpt)
    if len(positions) > limit:
        print(f"\n（残り {len(positions) - limit} 件は省略）")


def _dump_tables(soup: BeautifulSoup, *, limit: int) -> None:
    tables = soup.find_all("table")
    print(f"table 要素: {len(tables)} 個")
    for index, table in enumerate(tables[:limit], start=1):
        attrs = {k: v for k, v in table.attrs.items() if k in ("id", "class", "summary")}
        rows = table.find_all("tr")
        print(f"\n--- table {index} attrs={attrs} rows={len(rows)} ---")
        for row in rows[:12]:
            cells = row.find_all(["th", "td"])
            rendered = " | ".join(
                (cell.get_text(" ", strip=True) or "·")[:24] for cell in cells
            )
            print(f"  {rendered[:400]}")
        if len(rows) > 12:
            print(f"  （残り {len(rows) - 12} 行は省略）")


def _dump_selects(soup: BeautifulSoup) -> None:
    selects = soup.find_all("select")
    print(f"select 要素: {len(selects)} 個")
    for select in selects:
        name = select.get("name") or select.get("id") or "(無名)"
        print(f"\n--- select name={name!r} ---")
        for option in select.find_all("option")[:60]:
            print(
                f"  value={option.get('value')!r} "
                f"disabled={option.has_attr('disabled')} "
                f"text={option.get_text(' ', strip=True)!r}"
            )


def _dump_scripts(soup: BeautifulSoup, *, limit: int, chars: int) -> None:
    interesting = []
    for script in soup.find_all("script"):
        body = script.string or script.get_text() or ""
        if any(hint in body for hint in STOCK_HINTS):
            interesting.append(body)
    print(f"在庫関連らしき script: {len(interesting)} 個")
    for index, body in enumerate(interesting[:limit], start=1):
        squeezed = re.sub(r"\s{2,}", " ", body.strip())
        print(f"\n--- script {index} ({len(body)} 文字) ---")
        print(squeezed[:chars])


def run(url: str, *, needles: list[str], save_to: Path | None) -> int:
    page = fetch(url)

    _rule("レスポンス")
    print(f"requested : {page.requested_url}")
    print(f"final     : {page.final_url}")
    print(f"status    : {page.status_code}")
    print(f"encoding  : {page.encoding}")
    print(f"length    : {len(page.html)} 文字")

    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        save_to.write_text(page.html, encoding="utf-8")
        print(f"保存先    : {save_to}")

    soup = BeautifulSoup(page.html, "lxml")

    _rule("title / h1")
    if soup.title:
        print(f"title: {soup.title.get_text(' ', strip=True)}")
    for heading in soup.find_all(["h1", "h2"])[:5]:
        print(f"{heading.name}: {heading.get_text(' ', strip=True)[:120]}")

    _rule("table 構造")
    _dump_tables(soup, limit=8)

    _rule("select / option")
    _dump_selects(soup)

    _rule("script 内の在庫データらしきもの")
    _dump_scripts(soup, limit=6, chars=3000)

    for needle in needles:
        _rule(f"生 HTML 内の {needle!r} 周辺")
        _dump_context(page.html, needle, window=700, limit=6)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="調査する商品ページの URL")
    parser.add_argument(
        "--needle",
        action="append",
        default=None,
        help="生 HTML 内で周辺を確認したい文字列（複数指定可）",
    )
    parser.add_argument(
        "--save-html",
        type=Path,
        default=None,
        help="取得した HTML の保存先",
    )
    args = parser.parse_args(argv)
    needles = args.needle or ["LGY", "XL"]
    return run(args.url, needles=needles, save_to=args.save_html)


if __name__ == "__main__":
    sys.exit(main())
