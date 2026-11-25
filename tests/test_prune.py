"""Offline check on dropping old days from the detection index. No Home Assistant:

    python tests/test_prune.py

The index is kept in memory under (recorder, channel, day). Old days must be
dropped by their date. Comparing the wrong part of the key (the channel
number) against the date raised a TypeError at the end of every background
pass, so the daily photo clean-up after it never ran.

detections.py needs Home Assistant to import, so only `_forget_old_days` is
taken out of it and run with a stand-in clock.
"""

from __future__ import annotations

import ast
import asyncio
from datetime import date, timedelta
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[1] / "custom_components" / "hikvision_nvr" / "detections.py"
)
TODAY = date(2026, 11, 25)


class _Now:
    def date(self) -> date:
        return TODAY


class _DtUtil:
    @staticmethod
    def now() -> _Now:
        return _Now()


class _Hass:
    def __init__(self, store: dict) -> None:
        self.data = {"index": store}


def _function():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    node = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_forget_old_days"
    )
    scope = {"INDEX_KEY": "index", "dt_util": _DtUtil, "timedelta": timedelta}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope["_forget_old_days"]


def _entry(locked: bool = False) -> dict:
    lock = asyncio.Lock()
    if locked:
        asyncio.run(_take(lock))
    return {"lock": lock}


async def _take(lock: asyncio.Lock) -> None:
    await lock.acquire()


def main() -> None:
    forget = _function()
    old = (TODAY - timedelta(days=5)).isoformat()
    recent = (TODAY - timedelta(days=1)).isoformat()
    store = {
        ("nvr", 2, old): _entry(),
        ("nvr", 2, recent): _entry(),
        ("nvr", 5, old): _entry(locked=True),
    }
    forget(_Hass(store))
    assert ("nvr", 2, old) not in store, "an old day must be dropped"
    print("old day dropped                : ok")
    assert ("nvr", 2, recent) in store, "a recent day must stay"
    print("recent day kept                : ok")
    assert ("nvr", 5, old) in store, "a day being read (locked) must stay"
    print("locked old day kept            : ok")
    print("ALL PRUNE CHECKS PASSED")


if __name__ == "__main__":
    main()
