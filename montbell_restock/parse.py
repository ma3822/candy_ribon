"""商品ページから「色 × サイズ」ごとの在庫を読み取る。

モンベルのページはカラーを行、サイズを列に取った表で在庫を示している。
セルの表記（○ / × / 「カートに入れる」など）から在庫の有無を判定する。
表以外の持ち方をしていた場合に備えて、select 要素からの読み取りも試す。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

#: サイズ列のヘッダかどうかを判断するための語。
SIZE_TOKENS = frozenset(
    {
        "XS", "S", "M", "L", "XL", "XXL", "3XL",
        "SS", "LL", "3L", "4L",
        "F", "FREE", "ONESIZE",
    }
)

#: 在庫ありと読むべき語。含まれていれば当たりとみなす。
IN_STOCK_WORDS = (
    "在庫あり", "残りわずか", "お取り寄せ", "カートに入れる", "カートへ",
    "ご注文", "購入", "○", "◯", "△", "▲",
)

#: 在庫なしと読むべき語。含まれていれば当たりとみなす。
OUT_OF_STOCK_WORDS = (
    "在庫なし", "品切", "売り切れ", "在庫切れ", "完売", "販売終了",
    "入荷未定", "入荷予定", "予定なし", "取扱終了", "sold out", "soldout",
    "×", "✕", "☓",
)

#: セル全体がこれだけなら在庫なし。長音符「ー」は「カート」「グレー」のように
#: 語の一部として現れるので、部分一致で見てはいけない。
OUT_OF_STOCK_SYMBOLS = frozenset({"-", "－", "ー", "‐", "—", "–", "―", "‑"})


@dataclass(frozen=True)
class Variant:
    """1 つの「色 × サイズ」の組。"""

    color: str
    size: str
    #: True/False は判定できたとき、None は表記から判断できなかったとき。
    in_stock: bool | None
    #: 判定の根拠になった表記。ログや Issue 本文に出して後から検証できるようにする。
    marker: str


def normalize(text: str) -> str:
    """全角と半角、大文字小文字、空白の揺れを吸収する。"""
    folded = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", folded).strip().upper()


def _looks_like_size(text: str) -> bool:
    return normalize(text) in SIZE_TOKENS


def read_stock_marker(text: str) -> tuple[bool | None, str]:
    """セルの表記から在庫の有無を読む。(判定, 根拠になった表記) を返す。"""
    squeezed = re.sub(r"\s+", " ", (text or "")).strip()
    if squeezed in OUT_OF_STOCK_SYMBOLS:
        return False, squeezed

    lowered = squeezed.lower()
    # 「在庫なし」を先に見る。「在庫あり」と部分一致で衝突しないようにするため。
    for marker in OUT_OF_STOCK_WORDS:
        if marker.lower() in lowered:
            return False, squeezed
    for marker in IN_STOCK_WORDS:
        if marker.lower() in lowered:
            return True, squeezed
    return None, squeezed


def _cell_signal(cell: Tag) -> str:
    """セルの在庫表記を集める。画像 alt やボタンの文言も判断材料になる。"""
    parts = [cell.get_text(" ", strip=True)]
    for image in cell.find_all("img"):
        parts.extend([image.get("alt") or "", image.get("src") or ""])
    for control in cell.find_all(["button", "input", "a"]):
        parts.extend(
            [
                control.get("value") or "",
                control.get("title") or "",
                control.get("alt") or "",
            ]
        )
    return " ".join(part for part in parts if part)


def _variants_from_table(table: Tag) -> list[Variant]:
    """カラー行 × サイズ列の表を読む。"""
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    # サイズ見出しの行を探す。表の先頭が必ずしも見出しとは限らない。
    header_index = None
    sizes: list[tuple[int, str]] = []
    for index, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        found = [
            (position, normalize(cell.get_text(" ", strip=True)))
            for position, cell in enumerate(cells)
            if _looks_like_size(cell.get_text(" ", strip=True))
        ]
        if len(found) >= 2:
            header_index, sizes = index, found
            break

    if header_index is None:
        return []

    variants: list[Variant] = []
    for row in rows[header_index + 1 :]:
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        color = cells[0].get_text(" ", strip=True)
        if not color:
            continue

        for position, size in sizes:
            if position >= len(cells):
                continue
            cell = cells[position]
            # まずセルの文字だけで見る。「－」だけのセルを他の属性と混ぜて
            # 判定できなくならないようにするため。
            in_stock, marker = read_stock_marker(cell.get_text(" ", strip=True))
            if in_stock is None:
                in_stock, marker = read_stock_marker(_cell_signal(cell))
            variants.append(
                Variant(color=color, size=size, in_stock=in_stock, marker=marker)
            )

    return variants


def _variants_from_select(select: Tag) -> list[Variant]:
    """「カラー / サイズ」を 1 つの option にまとめている作りに備える。"""
    variants: list[Variant] = []
    for option in select.find_all("option"):
        label = option.get_text(" ", strip=True)
        if not label:
            continue

        # 「ライトグレー(LGY) / XL」のような表記を色とサイズに割る。
        parts = [part.strip() for part in re.split(r"[/／|｜]", label) if part.strip()]
        if len(parts) < 2:
            continue
        color, size = parts[0], normalize(parts[1])
        if not _looks_like_size(size):
            continue

        if option.has_attr("disabled"):
            variants.append(Variant(color, size, False, "option disabled"))
            continue

        in_stock, marker = read_stock_marker(label)
        # 表記が無いなら、選べること自体を在庫ありと読む。
        if in_stock is None:
            in_stock, marker = True, "選択可能な option"
        variants.append(Variant(color, size, in_stock, marker))

    return variants


def extract_variants(html: str) -> list[Variant]:
    soup = BeautifulSoup(html, "lxml")

    variants: list[Variant] = []
    for table in soup.find_all("table"):
        variants.extend(_variants_from_table(table))
    if variants:
        return variants

    for select in soup.find_all("select"):
        variants.extend(_variants_from_select(select))
    return variants


def _color_matches(variant_color: str, wanted: str) -> bool:
    """「LGY」が「ライトグレー(LGY)」にも当たるようにする。"""
    haystack = normalize(variant_color)
    needle = normalize(wanted)
    if not needle:
        return False
    if haystack == needle:
        return True
    # 単語として現れるときだけ当てる。BK が BKGY に当たらないようにするため。
    return re.search(rf"(?<![A-Z0-9]){re.escape(needle)}(?![A-Z0-9])", haystack) is not None


def find_variant(variants: list[Variant], *, color: str, size: str) -> Variant | None:
    wanted_size = normalize(size)
    for variant in variants:
        # サイズは完全一致で見る。XL が XXL に当たると困るため。
        if normalize(variant.size) == wanted_size and _color_matches(variant.color, color):
            return variant
    return None
