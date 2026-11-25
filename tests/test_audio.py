"""Offline check on which replays get sound. No Home Assistant:

    python tests/test_audio.py

Replays re-encode a camera's sound to AAC only when the recorder says it is
in a codec ffmpeg decodes reliably (G.711, AAC, PCM). Anything else, above all
G.722.1, and cameras with audio switched off, keep the old silent replay (-an).

api.py needs Home Assistant to import, so only `_audio_args` and the set it
reads are taken out of it.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "custom_components" / "hikvision_nvr" / "api.py"


def _function():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    wanted = []
    for node in tree.body:
        is_helper = isinstance(node, ast.FunctionDef) and node.name == "_audio_args"
        is_set = isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_SAFE_AUDIO" for t in node.targets
        )
        if is_helper or is_set:
            wanted.append(node)
    scope: dict = {}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope["_audio_args"]


def check(label: str, got, want_sound: bool) -> None:
    has = "-c:a" in got
    assert has == want_sound, f"{label}: got {got}"
    assert ("-an" in got) != want_sound, f"{label}: got {got}"
    print(f"{label:<34}: ok")


def main() -> None:
    audio = _function()
    cam = lambda on, codec: SimpleNamespace(has_audio=on, audio_codec=codec)  # noqa: E731
    check("G.711ulaw gets sound", audio(cam(True, "G.711ulaw")), True)
    check("G.711alaw gets sound", audio(cam(True, "G.711alaw")), True)
    check("AAC gets sound", audio(cam(True, "AAC")), True)
    check("G.722.1 stays silent", audio(cam(True, "G.722.1")), False)
    check("G.726 stays silent", audio(cam(True, "G.726")), False)
    check("audio off stays silent", audio(cam(False, "G.711ulaw")), False)
    check("unknown codec stays silent", audio(cam(True, None)), False)
    got = audio(cam(True, "G.711ulaw"))
    assert "0:a:0?" in got, "a recording without a sound track must still play"
    print("missing sound track tolerated    : ok")
    print("ALL AUDIO CHECKS PASSED")


if __name__ == "__main__":
    main()
