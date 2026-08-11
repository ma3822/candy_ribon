"""再入荷を知らせる先。

送り先は 3 つあり、それぞれ「使える状況なら使う」という判断を自分で持つ。

- デスクトップ通知: 手元のマシンで動かしているとき。すぐ気づけるのが利点。
- GitHub Issue: トークンがあるとき。消えない記録が残り、メールにも流れる。
- Webhook: URL を設定したとき。Slack / Discord に流したい場合に使う。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

import requests

GITHUB_API = "https://api.github.com"


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    url: str


def build_notification(
    *, name: str, color: str, size: str, url: str, detail: str
) -> Notification:
    title = f"再入荷: {name}（{color} / {size}）"
    body = "\n".join(
        [
            f"**{name}** の **{color} / {size}** が購入可能になりました。",
            "",
            f"- 商品ページ: {url}",
            f"- 判定の根拠: {detail}",
            "",
            "人気モデルは短時間で売り切れます。早めに確認してください。",
        ]
    )
    return Notification(title=title, body=body, url=url)


def _applescript_string(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def send_desktop(notification: Notification) -> str | None:
    """手元のマシンでデスクトップ通知を出す。CI 上では何もしない。"""
    if os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"):
        return None

    subtitle = notification.url
    if sys.platform == "darwin":
        script = (
            f"display notification {_applescript_string(subtitle)}"
            f" with title {_applescript_string(notification.title)}"
            f' sound name "Glass"'
        )
        subprocess.run(["osascript", "-e", script], check=False)
        return "デスクトップ通知"

    if sys.platform.startswith("linux") and shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", "--urgency=critical", notification.title, subtitle],
            check=False,
        )
        return "デスクトップ通知"

    return None


def send_github_issue(notification: Notification, *, labels: list[str] | None = None) -> str | None:
    """Issue を立てて URL を返す。トークンが無ければ何もしない。"""
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repository:
        return None

    response = requests.post(
        f"{GITHUB_API}/repos/{repository}/issues",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "title": notification.title,
            "body": notification.body,
            "labels": labels or ["restock"],
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("html_url")


def send_webhook(notification: Notification) -> str | None:
    """Slack / Discord 互換の Webhook に投げる。未設定なら何もしない。"""
    url = os.environ.get("RESTOCK_WEBHOOK_URL")
    if not url:
        return None

    text = f"{notification.title}\n{notification.url}"
    # Slack は "text"、Discord は "content" を読むので両方入れておく。
    response = requests.post(url, json={"text": text, "content": text}, timeout=30)
    response.raise_for_status()
    return "Webhook"


def dispatch(notification: Notification) -> list[str]:
    """使える通知手段すべてに送り、送れたものの一覧を返す。

    1 つ失敗しても他は試す。通知が主目的なので、
    どれか 1 つでも届くことを優先する。
    """
    results: list[str] = []
    for send in (send_desktop, send_github_issue, send_webhook):
        try:
            outcome = send(notification)
        except Exception as exc:  # 通知の失敗で監視自体を止めない
            results.append(f"{send.__name__} は失敗: {exc}")
            continue
        if outcome:
            results.append(outcome)
    return results
