"""Offline checks on the recording status reader. No Home Assistant, no network:

    python tests/test_status.py

Newer firmware answers /ISAPI/System/workingstatus?format=json; older firmware
only has the XML form. Both must give {channel: recording}.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hikvision_nvr"))

import isapi  # noqa: E402
from defusedxml import ElementTree as DET  # noqa: E402

JSON = '{"WorkingStatus": {"ChanStatus": [{"chanNo": 1, "record": 1}, {"chanNo": 2, "record": 0}]}}'
XML = """<WorkingStatus><ChanStatus><chanNo>1</chanNo><record>0</record></ChanStatus>
<ChanStatus><chanNo>5</chanNo><record>1</record></ChanStatus></WorkingStatus>"""


class Reply:
    def __init__(self, text: str) -> None:
        self._text = text

    async def text(self) -> str:
        return self._text


class Fake(isapi.HikvisionISAPI):
    def __init__(self, json_text: str | None) -> None:
        self.json_text = json_text

    async def request(self, method, path, **kwargs):
        if self.json_text is None:
            raise isapi.UnsupportedOperation(path)
        return Reply(self.json_text)

    async def get_xml(self, path: str):
        return DET.fromstring(XML)


def main() -> None:
    assert asyncio.run(Fake(JSON).async_recording_status()) == {1: True, 2: False}
    print("JSON working status            : ok")
    assert asyncio.run(Fake(None).async_recording_status()) == {1: False, 5: True}
    print("XML fallback                   : ok")
    got = asyncio.run(Fake("<html>not json</html>").async_recording_status())
    assert got == {1: False, 5: True}
    print("non-JSON answer falls back     : ok")
    print("ALL STATUS CHECKS PASSED")


if __name__ == "__main__":
    main()
