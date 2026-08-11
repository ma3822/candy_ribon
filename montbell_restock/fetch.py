"""モンベル ウェブショップの商品ページを取得する。

ページの文字コードが UTF-8 とは限らないため、Content-Type ヘッダ →
meta charset → 推定、の順で判定してからデコードする。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import requests

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

_HEADER_CHARSET = re.compile(r"charset=([A-Za-z0-9_\-]+)", re.I)
_META_CHARSET = re.compile(rb"""charset\s*=\s*["']?([A-Za-z0-9_\-]+)""", re.I)


class FetchError(RuntimeError):
    """ページ取得に失敗した（リトライを使い切った）ことを表す。"""


@dataclass(frozen=True)
class Page:
    requested_url: str
    final_url: str
    status_code: int
    encoding: str
    html: str


def _detect_encoding(response: requests.Response) -> str:
    header = _HEADER_CHARSET.search(response.headers.get("Content-Type", ""))
    if header:
        return header.group(1)
    meta = _META_CHARSET.search(response.content[:8192])
    if meta:
        return meta.group(1).decode("ascii", "ignore")
    return response.apparent_encoding or "utf-8"


def _decode(response: requests.Response, encoding: str) -> str:
    try:
        return response.content.decode(encoding, errors="replace")
    except LookupError:
        return response.content.decode("utf-8", errors="replace")


def fetch(
    url: str,
    *,
    timeout: float = 30.0,
    attempts: int = 4,
    session: requests.Session | None = None,
) -> Page:
    """`url` を取得する。5xx とネットワークエラーは指数バックオフで再試行する。"""
    sess = session or requests.Session()
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = sess.get(url, headers=headers, timeout=timeout)
            if response.status_code >= 500:
                raise FetchError(f"HTTP {response.status_code}")
            encoding = _detect_encoding(response)
            return Page(
                requested_url=url,
                final_url=response.url,
                status_code=response.status_code,
                encoding=encoding,
                html=_decode(response, encoding),
            )
        except (requests.RequestException, FetchError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(2**attempt)

    raise FetchError(f"{url} の取得に失敗しました: {last_error}")
