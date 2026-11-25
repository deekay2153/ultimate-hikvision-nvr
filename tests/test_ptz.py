"""Offline checks on the PTZ preset list. No Home Assistant, no network:

    python tests/test_ptz.py

A Hikvision PTZ reports every preset slot as enabled with a default name, and
some numbers are commands (94 = remote reboot). Only presets someone named may
be offered, and never a command number.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hikvision_nvr"))

import isapi  # noqa: E402
from defusedxml import ElementTree as DET  # noqa: E402

REPLY = """<PTZPresetList>
<PTZPreset><enabled>true</enabled><id>1</id><presetName></presetName></PTZPreset>
<PTZPreset><enabled>true</enabled><id>2</id><presetName>Preset 2</presetName></PTZPreset>
<PTZPreset><enabled>true</enabled><id>3</id><presetName>Driveway</presetName></PTZPreset>
<PTZPreset><enabled>false</enabled><id>4</id><presetName>Old view</presetName></PTZPreset>
<PTZPreset><enabled>true</enabled><id>33</id><presetName>Auto-flip</presetName></PTZPreset>
<PTZPreset><enabled>true</enabled><id>94</id><presetName>Remote reboot</presetName></PTZPreset>
<PTZPreset><enabled>true</enabled><id>120</id><presetName>Gate</presetName></PTZPreset>
</PTZPresetList>"""


class Fake(isapi.HikvisionISAPI):
    def __init__(self) -> None:  # no session, no network
        pass

    async def get_xml(self, path: str):
        return DET.fromstring(REPLY)


def main() -> None:
    got = asyncio.run(Fake().async_ptz_presets(1))
    want = [{"id": 3, "name": "Driveway"}, {"id": 120, "name": "Gate"}]
    assert got == want, got
    assert 94 in isapi.PTZ_COMMAND_PRESETS
    print("named only, commands never     : ok")
    print("ALL PTZ CHECKS PASSED")


if __name__ == "__main__":
    main()
