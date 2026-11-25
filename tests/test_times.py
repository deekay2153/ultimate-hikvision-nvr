"""Offline checks on recorder time handling. No Home Assistant, no network:

    python tests/test_times.py

Hikvision search and playback times are the recorder's own wall-clock time,
even when written with a trailing Z. Reading them as UTC put every recording
hours out anywhere but UTC (the original 1.0.0 behaviour). These checks pin the
local-time reading, including across a daylight-saving change.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hikvision_nvr"))

import isapi  # noqa: E402

SYDNEY = ZoneInfo("Australia/Sydney")


def check(label: str, got: object, want: object) -> None:
    assert got == want, f"{label}: got {got!r}, want {want!r}"
    print(f"{label:<34}: ok")


def main() -> None:
    isapi.set_local_timezone(SYDNEY)

    # Summer (AEDT, UTC+11): 23:00:43 on the recorder's clock is 12:00:43 UTC.
    check(
        "Z time read as local (summer)",
        isapi._parse_time("2026-11-24T23:00:43Z"),
        datetime(2026, 11, 24, 12, 0, 43, tzinfo=UTC),
    )
    # Winter (AEST, UTC+10).
    check(
        "Z time read as local (winter)",
        isapi._parse_time("2026-06-01T10:00:00Z"),
        datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC),
    )
    # Compact playback form.
    check(
        "compact form read as local",
        isapi._parse_time("20261124T230043Z"),
        datetime(2026, 11, 24, 12, 0, 43, tzinfo=UTC),
    )
    # A real offset is kept as written.
    check(
        "explicit offset kept",
        isapi._parse_time("2026-11-24T23:00:43+10:00"),
        datetime(2026, 11, 24, 13, 0, 43, tzinfo=UTC),
    )
    # Writing goes back to the recorder's clock.
    moment = datetime(2026, 11, 24, 12, 0, 43, tzinfo=UTC)
    check("written as local", isapi.to_isapi_time(moment), "2026-11-24T23:00:43Z")
    check("round trip", isapi._parse_time(isapi.to_isapi_time(moment)), moment)
    # Across the April change (clocks back 03:00 AEDT -> 02:00 AEST, 5 Apr 2026).
    before = datetime(2026, 4, 4, 15, 30, tzinfo=UTC)  # 02:30 AEDT
    after = datetime(2026, 4, 4, 17, 30, tzinfo=UTC)  # 03:30 AEST
    check("DST: before the change", isapi.to_isapi_time(before), "2026-04-05T02:30:00Z")
    check("DST: after the change", isapi.to_isapi_time(after), "2026-04-05T03:30:00Z")

    # Default is UTC until the integration sets the zone.
    isapi.set_local_timezone(UTC)
    check("UTC default", isapi.to_isapi_time(moment), "2026-11-24T12:00:43Z")
    print("ALL TIME CHECKS PASSED")


if __name__ == "__main__":
    main()
