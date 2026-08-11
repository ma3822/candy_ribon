import pytest

from montbell_restock import notify


@pytest.fixture
def message():
    return notify.build_notification(
        name="テスト商品",
        color="LGY",
        size="XL",
        url="https://example.test/goods",
        detail="表記: '在庫あり'",
    )


def test_通知の文面に色とサイズと商品URLが入る(message):
    assert "LGY" in message.title
    assert "XL" in message.title
    assert "https://example.test/goods" in message.body


def test_送り先が未設定なら何も送らない(monkeypatch, message):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("RESTOCK_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("CI", "1")  # デスクトップ通知を抑止する

    assert notify.dispatch(message) == []


def test_ひとつ失敗しても他の送り先は試す(monkeypatch, message):
    monkeypatch.setattr(notify, "send_desktop", lambda n: (_ for _ in ()).throw(RuntimeError("画面なし")))
    monkeypatch.setattr(notify, "send_github_issue", lambda n, **kw: "https://example.test/issue/1")
    monkeypatch.setattr(notify, "send_webhook", lambda n: None)

    results = notify.dispatch(message)

    assert any("失敗" in result for result in results)
    assert "https://example.test/issue/1" in results


def test_CI上ではデスクトップ通知を出さない(monkeypatch, message):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert notify.send_desktop(message) is None
