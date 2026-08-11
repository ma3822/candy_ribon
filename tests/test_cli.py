"""通知の出しかたを固定するテスト。

肝心なのは「在庫なし → 在庫あり」に変わった 1 回だけ知らせること。
毎回のチェックで通知が飛んだり、逆に一度売り切れて再入荷したときに
黙ってしまったりしないことを確かめる。
"""

import json
from pathlib import Path

import pytest

from montbell_restock import cli, notify
from montbell_restock.fetch import Page

FIXTURES = Path(__file__).parent / "fixtures"

# fixture では LGY/XL が在庫なし、LGY/XXL が在庫ありになっている。
TABLE_HTML = (FIXTURES / "color_size_table.html").read_text(encoding="utf-8")


@pytest.fixture
def watchlist(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "テスト商品",
                        "name": "テスト商品",
                        "url": "https://example.test/goods",
                        "color": "LGY",
                        "size": "XL",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def sent(monkeypatch):
    """通知の送信先を差し替えて、飛んだ回数を数える。"""
    calls = []

    def record(notification):
        calls.append(notification)
        return ["テスト用の送り先"]

    monkeypatch.setattr(notify, "dispatch", record)
    return calls


def serve(monkeypatch, html):
    monkeypatch.setattr(
        cli,
        "fetch",
        lambda url, **kwargs: Page(url, url, 200, "utf-8", html),
    )


def run_check(watchlist, state_path):
    return cli.main(["check", "--watchlist", str(watchlist), "--state", str(state_path)])


def test_在庫なしのままなら通知しない(monkeypatch, watchlist, sent, tmp_path):
    serve(monkeypatch, TABLE_HTML)
    state_path = tmp_path / "state.json"

    assert run_check(watchlist, state_path) == 0
    assert run_check(watchlist, state_path) == 0
    assert sent == []


def test_在庫ありに変わったら一度だけ通知する(monkeypatch, watchlist, sent, tmp_path):
    state_path = tmp_path / "state.json"

    serve(monkeypatch, TABLE_HTML)
    run_check(watchlist, state_path)
    assert sent == []

    # LGY/XL が在庫ありに変わったページを返すようにする。
    serve(monkeypatch, TABLE_HTML.replace("<td>在庫なし</td>", "<td>在庫あり</td>"))
    run_check(watchlist, state_path)
    assert len(sent) == 1
    assert "LGY" in sent[0].title and "XL" in sent[0].title

    # 在庫ありが続いている間は、何度チェックしても通知は増えない。
    run_check(watchlist, state_path)
    run_check(watchlist, state_path)
    assert len(sent) == 1


def test_売り切れて再入荷したらまた通知する(monkeypatch, watchlist, sent, tmp_path):
    state_path = tmp_path / "state.json"
    in_stock = TABLE_HTML.replace("<td>在庫なし</td>", "<td>在庫あり</td>")

    serve(monkeypatch, in_stock)
    run_check(watchlist, state_path)
    assert len(sent) == 1

    serve(monkeypatch, TABLE_HTML)
    run_check(watchlist, state_path)
    assert len(sent) == 1

    serve(monkeypatch, in_stock)
    run_check(watchlist, state_path)
    assert len(sent) == 2


def test_ページを読めないときは失敗として終える(monkeypatch, watchlist, sent, tmp_path):
    serve(monkeypatch, "<html><body>メンテナンス中</body></html>")
    state_path = tmp_path / "state.json"

    # 気づかないまま監視が死ぬのを避けるため、終了コードで失敗を知らせる。
    assert run_check(watchlist, state_path) == 1
    assert sent == []


def test_扱いの無い組み合わせは在庫ありと誤判定しない(monkeypatch, watchlist, sent, tmp_path):
    serve(monkeypatch, TABLE_HTML.replace("ライトグレー(LGY)", "ネイビー(NV)"))
    state_path = tmp_path / "state.json"

    assert run_check(watchlist, state_path) == 1
    assert sent == []
