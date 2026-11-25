"""PATCH (not upstream): person / vehicle detections for the timeline.

The NVR's event search returns the same people and vehicle detections the
Hik-Connect app draws on its timeline, each with a snapshot. These views expose
them to the card. Read-only towards the NVR: searches and picture fetches.

Index: asking the NVR for a whole day of detections is slow (up to half a
minute on a busy camera), so the answers are kept here, one list per camera
per day, in memory and under <media>/hikvision_nvr/index. A request only asks
the NVR for the minutes since the list was last brought up to date. A finished
day is never searched again.

Thumbnails: the NVR's stills are full size and slow to hand out, so a small
copy of each is kept under <media>/hikvision_nvr/thumbs and served from there.

A background pass every few minutes brings today's lists up to date and makes
the missing thumbnails, so both are ready when someone opens History.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import time
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from aiohttp import web
from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import _BaseView, _get_channel, _get_coordinator, _handle_errors, _time_range
from .const import DOMAIN
from .coordinator import async_coordinators

_LOGGER = logging.getLogger(__name__)

KINDS = {"peopleDetection": "person", "vehicleMatchResult": "vehicle"}
PAGE = 50
MAX_PAGES = 40
SEARCH_PATH = "/ISAPI/ContentMgmt/eventRecordSearch?format=json"
AMP = chr(38)
SAFE_NAME = re.compile(r"^[A-Za-z0-9_]{8,120}$")
TRACK_IN_PATH = re.compile(r"/tracks/(\d{3,5})/?$")

THUMB_WIDTH = 320
THUMB_KEEP_SECONDS = 7 * 86400
INDEX_KEEP_SECONDS = 30 * 86400
PREFETCH_EVERY = timedelta(minutes=5)
PREFETCH_CHANNELS = (1, 2, 5, 6, 7, 8, 9, 10)
PREFETCH_MAX = 80
VISIT_GAP = 60

INDEX_KEY = f"{DOMAIN}_detection_index"
INDEX_CHUNK = timedelta(hours=3)
INDEX_OVERLAP = timedelta(minutes=3)
INDEX_FRESH_SECONDS = 45


def _later(when, delta):
    """when plus delta."""
    return when - (delta * -1)


def _stamp(value) -> str:
    """Local time with its real offset, which is what this search expects."""
    return dt_util.as_local(value).isoformat(timespec="seconds")


def _picture_ref(url: str | None) -> str | None:
    """Turn the NVR's own picture URL into a path-safe 'track/name/size'."""
    if not url:
        return None
    try:
        parts = urlsplit(url)
        track = TRACK_IN_PATH.search(parts.path)
        query = parse_qs(parts.query)
        name = query.get("name", [""])[0]
        size = query.get("size", [""])[0]
        if track and SAFE_NAME.match(name) and size.isdigit():
            return f"{track.group(1)}/{name}/{size}"
    except ValueError:
        pass
    return None


def _valid_ref(track: str, name: str, size: str) -> bool:
    return bool(track.isdigit() and size.isdigit() and SAFE_NAME.match(name))


async def _search(coordinator, channel_id: int, start, end):
    """All person / vehicle detections for one channel in a time range."""
    search_id = str(uuid.uuid4())
    found = []
    position = 0
    truncated = False
    for page in range(MAX_PAGES):
        body = json.dumps(
            {
                "EventSearchDescription": {
                    "searchID": search_id,
                    "searchResultPosition": position,
                    "maxResults": PAGE,
                    "timeSpanList": [
                        {"startTime": _stamp(start), "endTime": _stamp(end)}
                    ],
                    "type": "all",
                    "channels": [channel_id],
                    "eventType": "all",
                }
            }
        )
        response = await coordinator.api.request("POST", SEARCH_PATH, data=body)
        result = json.loads(await response.text()).get("EventSearchResult", {})
        targets = result.get("Targets") or []
        for item in targets:
            kind = KINDS.get(item.get("eventType"))
            if kind is None:
                continue
            raw = item.get("alarmStartTime") or item.get("startTime") or ""
            when = dt_util.parse_datetime(raw)
            if when is None:
                continue
            found.append(
                {
                    "time": dt_util.as_utc(when).isoformat(),
                    "kind": kind,
                    "picture": _picture_ref(item.get("pictureUrl")),
                }
            )
        position = sum((position, len(targets)))
        if not targets or result.get("responseStatusStrg") != "MORE":
            break
    else:
        truncated = True
    found.sort(key=lambda entry: entry["time"])
    return found, truncated


# ------------------------------------------------------------------ index


def _media_dir(hass) -> Path:
    media = Path(hass.config.media_dirs.get("local", hass.config.path("media")))
    return media / DOMAIN


def _index_path(hass, channel_id: int, day) -> Path:
    return _media_dir(hass) / "index" / f"{channel_id}_{day.isoformat()}.json"


def _day_bounds(day):
    """Local midnight to the next local midnight."""
    start = dt_util.start_of_local_day(day)
    end = dt_util.start_of_local_day(_later(day, timedelta(days=1)))
    return dt_util.as_utc(start), dt_util.as_utc(end)


def _load_index(path: Path):
    """Runs in the executor."""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (OSError, ValueError):
        pass
    return None


def _save_index(path: Path, payload: dict) -> None:
    """Runs in the executor."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_text(json.dumps(payload))
    partial.replace(path)


async def _day_detections(hass, coordinator, channel_id: int, day, max_age=INDEX_FRESH_SECONDS):
    """One camera's detections for one local day, from the kept list.

    Only the stretch since the list was last brought up to date is asked of
    the NVR, in chunks, and never anything for a day that is already complete.
    """
    store = hass.data.setdefault(INDEX_KEY, {})
    key = (channel_id, day.isoformat())
    entry = store.get(key)
    if entry is None:
        entry = {"items": [], "until": None, "loaded": False, "lock": asyncio.Lock()}
        store[key] = entry
    async with entry["lock"]:
        start, end = _day_bounds(day)
        path = _index_path(hass, channel_id, day)
        if not entry["loaded"]:
            saved = await hass.async_add_executor_job(_load_index, path)
            if saved:
                entry["items"] = saved.get("items") or []
                entry["until"] = dt_util.parse_datetime(saved.get("until") or "")
            entry["loaded"] = True
        now = dt_util.utcnow()
        until = entry["until"]
        if until is not None and until >= end:
            return entry["items"]
        if until is not None and (now - until).total_seconds() < max_age:
            return entry["items"]
        if start >= now:
            return entry["items"]
        cursor = start if until is None else max(start, until - INDEX_OVERLAP)
        stop = min(end, now)
        seen = {(i["time"], i["kind"], i["picture"]) for i in entry["items"]}
        changed = False
        try:
            while cursor < stop:
                chunk_end = min(stop, _later(cursor, INDEX_CHUNK))
                found, _ = await _search(coordinator, channel_id, cursor, chunk_end)
                for item in found:
                    ident = (item["time"], item["kind"], item["picture"])
                    if ident in seen:
                        continue
                    seen.add(ident)
                    entry["items"].append(item)
                    changed = True
                entry["until"] = chunk_end
                cursor = chunk_end
        finally:
            if changed:
                entry["items"].sort(key=lambda i: i["time"])
            done = entry["until"] is not None and entry["until"] >= end
            if entry["until"] is not None and (changed or done or until is None):
                payload = {"until": entry["until"].isoformat(), "items": entry["items"]}
                try:
                    await hass.async_add_executor_job(_save_index, path, payload)
                except OSError as err:
                    _LOGGER.debug(f"Detection list not saved ({path.name}): {err!r}")
        return entry["items"]


def _forget_old_days(hass) -> None:
    """Keep only recent days in memory; the files stay on disk."""
    store = hass.data.get(INDEX_KEY) or {}
    cutoff = (dt_util.now().date() - timedelta(days=3)).isoformat()
    for key in [k for k in store if k[1] < cutoff]:
        if not store[key]["lock"].locked():
            store.pop(key, None)


# ------------------------------------------------------------- thumbnails


def _thumb_dir(hass) -> Path:
    return _media_dir(hass) / "thumbs"


def _thumb_path(hass, track: str, name: str) -> Path:
    return _thumb_dir(hass) / f"{track}_{name}.jpg"


def _make_thumb(data: bytes, target: Path) -> bytes:
    """Shrink a full-size still and keep the small copy. Runs in the executor."""
    from PIL import Image

    image = Image.open(io.BytesIO(data)).convert("RGB")
    height = max(1, round(image.height * THUMB_WIDTH / image.width))
    image = image.resize((THUMB_WIDTH, height))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=72)
    small = out.getvalue()
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    partial.write_bytes(small)
    partial.replace(target)
    return small


def _read_if_present(target: Path) -> bytes | None:
    return target.read_bytes() if target.exists() else None


def _list_names(folder: Path) -> set:
    """Runs in the executor."""
    if not folder.exists():
        return set()
    return {file.name for file in folder.glob("*.jpg")}


def _prune(folder: Path, pattern: str, keep_seconds: int) -> int:
    """Drop files older than the keep period. Runs in the executor."""
    removed = []
    if not folder.exists():
        return 0
    now = time.time()
    for file in folder.glob(pattern):
        try:
            if now - file.stat().st_mtime > keep_seconds:
                file.unlink()
                removed.append(file)
        except OSError:
            continue
    return len(removed)


async def _thumb(hass, coordinator, track: str, name: str, size: str) -> bytes:
    target = _thumb_path(hass, track, name)
    cached = await hass.async_add_executor_job(_read_if_present, target)
    if cached is not None:
        return cached
    path = f"/picture/Streaming/tracks/{track}/?name={name}{AMP}size={size}"
    data = await coordinator.api.get_bytes(path)
    return await hass.async_add_executor_job(_make_thumb, data, target)


def async_start_prefetch(hass) -> None:
    """Keep the detection lists and thumbnails ready. Idempotent."""
    key = f"{DOMAIN}_thumb_prefetch"
    if hass.data.get(key):
        return
    state = {"busy": False, "pruned": 0.0}

    async def run() -> None:
        if state["busy"]:
            return
        state["busy"] = True
        made = []
        try:
            today = dt_util.now().date()
            days = (today, today - timedelta(days=1))
            have = await hass.async_add_executor_job(_list_names, _thumb_dir(hass))
            for coordinator in async_coordinators(hass).values():
                for day in days:
                    for channel_id in PREFETCH_CHANNELS:
                        try:
                            found = await _day_detections(
                                hass, coordinator, channel_id, day, max_age=0
                            )
                        except Exception as err:
                            _LOGGER.debug(f"Detection pass: search failed ch {channel_id}: {err!r}")
                            continue
                        last = {}
                        for item in list(found):
                            ref = item.get("picture")
                            if not ref:
                                continue
                            when = dt_util.parse_datetime(item["time"]).timestamp()
                            previous = last.get(item["kind"])
                            last[item["kind"]] = when
                            # One per visit, the same rule the card uses.
                            if previous is not None and when - previous < VISIT_GAP:
                                continue
                            track, name, size = ref.split("/")
                            if f"{track}_{name}.jpg" in have:
                                continue
                            if len(made) >= PREFETCH_MAX:
                                break
                            try:
                                await _thumb(hass, coordinator, track, name, size)
                                made.append(ref)
                            except Exception as err:
                                _LOGGER.debug(f"Detection pass: fetch failed {ref}: {err!r}")
                            await asyncio.sleep(0.1)
            _forget_old_days(hass)
            if time.time() - state["pruned"] > 86400:
                state["pruned"] = time.time()
                await hass.async_add_executor_job(
                    _prune, _thumb_dir(hass), "*.jpg", THUMB_KEEP_SECONDS
                )
                await hass.async_add_executor_job(
                    _prune, _media_dir(hass) / "index", "*.json", INDEX_KEEP_SECONDS
                )
            if made:
                _LOGGER.debug(f"Detection pass: made {len(made)} thumbnails")
        except Exception as err:
            _LOGGER.warning(f"Detection pass failed: {err!r}")
        finally:
            state["busy"] = False
        if len(made) >= PREFETCH_MAX:
            # More to make: carry on shortly instead of waiting for the next pass.
            async_call_later(hass, 20, kick)

    @callback
    def kick(now=None) -> None:
        # A background task, so a long first pass never holds up start-up.
        hass.async_create_background_task(run(), f"{DOMAIN}_detection_pass")

    hass.data[key] = async_track_time_interval(hass, kick, PREFETCH_EVERY)
    async_call_later(hass, 120, kick)


# ------------------------------------------------------------------ views


class DetectionsView(_BaseView):
    """GET /api/hikvision_nvr/{device_id}/{channel}/detections (start, end)."""

    url = "/api/hikvision_nvr/{device_id}/{channel}/detections"
    name = "api:hikvision_nvr:detections"

    @_handle_errors
    async def get(self, request, device_id, channel):
        hass = request.app["hass"]
        coordinator = _get_coordinator(hass, device_id)
        chan = _get_channel(coordinator, channel)
        start, end = _time_range(request)
        truncated = False
        try:
            day = dt_util.as_local(start).date()
            day_start, day_end = _day_bounds(day)
            if dt_util.as_utc(end) <= day_end:
                # Within one local day: answer from the kept list.
                low = dt_util.as_utc(start).replace(microsecond=0).isoformat()
                high = dt_util.as_utc(end).replace(microsecond=0).isoformat()
                items = await _day_detections(hass, coordinator, chan.id, day)
                found = [i for i in items if low <= i["time"] <= high]
            else:
                found, truncated = await _search(coordinator, chan.id, start, end)
        except Exception as err:
            _LOGGER.warning(f"Detection search failed for channel {chan.id}: {err!r}")
            raise
        return self.json(
            {
                "channel": chan.id,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "truncated": truncated,
                "detections": found,
            }
        )


class DetectionPictureView(_BaseView):
    """GET .../{channel}/detection_picture/{track}/{name}/{size}.jpg

    The full-size snapshot the NVR saved for one detection. Everything is in
    the path so the card can sign it (auth/sign_path) and use it as an image.
    """

    url = (
        "/api/hikvision_nvr/{device_id}/{channel}"
        "/detection_picture/{track}/{name}/{size}.jpg"
    )
    name = "api:hikvision_nvr:detection_picture"

    @_handle_errors
    async def get(self, request, device_id, channel, track, name, size):
        coordinator = _get_coordinator(request.app["hass"], device_id)
        _get_channel(coordinator, channel)
        if not _valid_ref(track, name, size):
            raise web.HTTPBadRequest(reason="bad picture reference")
        path = f"/picture/Streaming/tracks/{track}/?name={name}{AMP}size={size}"
        try:
            data = await coordinator.api.get_bytes(path)
        except Exception as err:
            _LOGGER.warning(f"Detection picture failed ({track}): {err!r}")
            raise
        return web.Response(
            body=data,
            content_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=86400"},
        )


class DetectionThumbView(_BaseView):
    """GET .../{channel}/detection_thumb/{track}/{name}/{size}.jpg

    The small cached copy of a detection snapshot (made on first request, or
    ahead of time by the background pass).
    """

    url = (
        "/api/hikvision_nvr/{device_id}/{channel}"
        "/detection_thumb/{track}/{name}/{size}.jpg"
    )
    name = "api:hikvision_nvr:detection_thumb"

    @_handle_errors
    async def get(self, request, device_id, channel, track, name, size):
        hass = request.app["hass"]
        coordinator = _get_coordinator(hass, device_id)
        _get_channel(coordinator, channel)
        if not _valid_ref(track, name, size):
            raise web.HTTPBadRequest(reason="bad picture reference")
        try:
            data = await _thumb(hass, coordinator, track, name, size)
        except Exception as err:
            _LOGGER.warning(f"Detection thumbnail failed ({track}): {err!r}")
            raise
        return web.Response(
            body=data,
            content_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=604800"},
        )
