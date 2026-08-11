"""再入荷を知らせる先。

既定は GitHub の Issue。リポジトリの通知設定でメール・モバイル通知に
そのまま流れるので、追加の設定なしで使えるのが理由。
`RESTOCK_WEBHOOK_URL` があれば Slack / Discord 互換の Webhook にも投げる。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests

GITHUB_API = "https://api.github.com"


@dataclass(frozen=True)
class Notification:
    title: str
    body: str


def build_notification(*, name: str, color: str, size: str, url: str, detail: str) -> Notification:
    title = f"再入荷: {name}（{color} / {size}）"
    body = "\n".join(
        [
            f"**{name}** の **{color} / {size}** が購入可能になりました。",
            "",
            f"- 商品ページ: {url}",
            f"- 判定根拠: {detail}",
            "",
            "モンベルの人気モデルはすぐ売り切れるので、早めの確認をおすすめします。",
        ]
    )
    return Notification(title=title, body=body)


def send_github_issue(notification: Notification, *, labels: list[str] | None = None) -> str | None:
    """Issue を立てて URL を返す。必要な環境変数が無ければ何もしない。"""
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repository:
        print("GITHUB_TOKEN / GITHUB_REPOSITORY が無いので Issue 作成はスキップします")
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


def send_webhook(notification: Notification) -> bool:
    """Slack / Discord 互換の Webhook に投げる。未設定なら何もしない。"""
    url = os.environ.get("RESTOCK_WEBHOOK_URL")
    if not url:
        return False

    text = f"{notification.title}\n\n{notification.body}"
    # Slack は "text"、Discord は "content" を見るので両方入れておく。
    response = requests.post(url, json={"text": text, "content": text}, timeout=30)
    response.raise_for_status()
    return True
