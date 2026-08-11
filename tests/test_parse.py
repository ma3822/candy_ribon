from pathlib import Path

import pytest

from montbell_restock.parse import (
    extract_variants,
    find_variant,
    normalize,
    read_stock_marker,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("在庫あり", True),
        ("残りわずか", True),
        ("カートに入れる", True),
        ("○", True),
        ("在庫なし", False),
        ("×", False),
        ("－", False),
        ("SOLD OUT", False),
        ("入荷未定", False),
        ("", None),
        ("送料について", None),
    ],
)
def test_在庫表記から在庫の有無を読める(text, expected):
    assert read_stock_marker(text)[0] is expected


def test_在庫なしを在庫ありより先に判定する():
    # 「在庫なし」は「在庫」を含むので、順番を誤ると在庫ありに倒れる。
    assert read_stock_marker("在庫なし")[0] is False


def test_全角と半角の揺れを吸収する():
    assert normalize("ＸＬ") == "XL"
    assert normalize("  xl ") == "XL"


class Test色サイズ表:
    def test_表から全ての組み合わせを読む(self):
        variants = extract_variants(load("color_size_table.html"))
        assert len(variants) == 15  # 3 色 × 5 サイズ

    def test_目的の色とサイズを引ける(self):
        variants = extract_variants(load("color_size_table.html"))
        variant = find_variant(variants, color="LGY", size="XL")
        assert variant is not None
        assert variant.in_stock is False

    def test_XLがXXLに当たらない(self):
        variants = extract_variants(load("color_size_table.html"))
        assert find_variant(variants, color="LGY", size="XL").in_stock is False
        assert find_variant(variants, color="LGY", size="XXL").in_stock is True

    def test_色コードで色名つきの表記に当てられる(self):
        variants = extract_variants(load("color_size_table.html"))
        assert find_variant(variants, color="BK", size="XL").in_stock is True

    def test_画像のaltからも在庫を読む(self):
        variants = extract_variants(load("color_size_table.html"))
        assert find_variant(variants, color="SURD", size="XL").in_stock is True

    def test_扱いのない組み合わせはNoneを返す(self):
        variants = extract_variants(load("color_size_table.html"))
        assert find_variant(variants, color="LGY", size="XS") is None


class Testselect形式:
    def test_disabledなoptionは在庫なしと読む(self):
        variants = extract_variants(load("variant_select.html"))
        assert find_variant(variants, color="LGY", size="XL").in_stock is False

    def test_選べるoptionは在庫ありと読む(self):
        variants = extract_variants(load("variant_select.html"))
        assert find_variant(variants, color="LGY", size="XXL").in_stock is True

    def test_サイズを含まないoptionは無視する(self):
        variants = extract_variants(load("variant_select.html"))
        assert all(variant.size for variant in variants)
        assert len(variants) == 3
