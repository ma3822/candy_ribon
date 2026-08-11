"""前回チェック時の在庫状態を JSON で持ち回すための小さな層。

「在庫なし → 在庫あり」に変わった瞬間だけ通知したいので、前回の状態を
リポジトリ内のファイルに残してコミットしていく。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

IN_STOCK = "in_stock"
OUT_OF_STOCK = "out_of_stock"
UNKNOWN = "unknown"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ItemState:
    status: str = UNKNOWN
    detail: str = ""
    checked_at: str = ""
    changed_at: str = ""
    #: 直近の「在庫あり」について通知済みかどうか。在庫なしに戻ると空に戻す。
    notified_at: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "ItemState":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class Store:
    path: Path
    items: dict[str, ItemState] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Store":
        if not path.exists():
            return cls(path=path, items={})
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
        items = {
            key: ItemState.from_dict(value)
            for key, value in raw.get("items", {}).items()
        }
        return cls(path=path, items=items)

    def get(self, item_id: str) -> ItemState:
        return self.items.get(item_id, ItemState())

    def record(self, item_id: str, *, status: str, detail: str) -> tuple[ItemState, bool]:
        """新しい観測を書き込み、(更新後の状態, 状態が変わったか) を返す。"""
        previous = self.get(item_id)
        changed = previous.status != status

        updated = ItemState(
            status=status,
            detail=detail,
            checked_at=now_iso(),
            changed_at=now_iso() if changed else (previous.changed_at or now_iso()),
            notified_at="" if status != IN_STOCK else previous.notified_at,
        )
        self.items[item_id] = updated
        return updated, changed

    def mark_notified(self, item_id: str) -> None:
        self.items[item_id].notified_at = now_iso()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": now_iso(),
            "items": {
                key: asdict(value) for key, value in sorted(self.items.items())
            },
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
