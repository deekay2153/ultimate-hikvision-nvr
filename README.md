<img src="custom_components/hikvision_nvr/brand/logo.png" alt="Hikvision NVR for Home Assistant" width="420">

# Ultimate Hikvision NVR for Home Assistant

[![Validate](https://github.com/deekay2153/ultimate-hikvision-nvr/actions/workflows/validate.yml/badge.svg)](https://github.com/deekay2153/ultimate-hikvision-nvr/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/deekay2153/ultimate-hikvision-nvr?sort=semver)](https://github.com/deekay2153/ultimate-hikvision-nvr/releases)
[![HACS: custom](https://img.shields.io/badge/HACS-custom-41BDF5.svg)](https://hacs.xyz/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.2%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-FFDD00?logo=buymeacoffee&logoColor=black)](https://www.buymeacoffee.com/deekay2153)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-black.svg)](LICENSE)

![Ultimate Hikvision NVR card: a camera wall with live tiles, a 24-hour bar of people and vehicles, and a detections list](https://raw.githubusercontent.com/deekay2153/ultimate-hikvision-nvr-card/main/docs/wall.jpg)

<sub>Shown with the [Ultimate Hikvision NVR card](https://github.com/deekay2153/ultimate-hikvision-nvr-card), camera pictures blurred with its screenshot mode.</sub>

Live view, recorded-history playback with **person and vehicle markers**, PTZ
with tap-to-aim, motion events and a full REST API for a Hikvision NVR/DVR — as
a native Home Assistant integration, added from the UI.

This is a fork of [techmarkai/hikvision-nvr-ha](https://github.com/techmarkai/hikvision-nvr-ha)
1.0.0 (MIT), with the fixes from running it every day on a real recorder. It
keeps the same domain (`hikvision_nvr`), so it replaces the original in place.
It is also the back end for the **[Ultimate Hikvision NVR card](https://github.com/deekay2153/ultimate-hikvision-nvr-card)**,
a camera wall with a live grid, a PTZ joystick and a detections timeline.

Verified on a 10-channel Hikvision NVR with a dual-lens PTZ, H.265 main streams
and H.264 sub streams, on Home Assistant 2026.11; the original was developed on
a DS-7608NI-K2/8P, firmware V4.40.015. Capabilities are read from the device
rather than assumed, so other ISAPI models work to the extent their firmware
exposes the same surfaces. Reports from other models are welcome.

## What this fork changes

| | |
|---|---|
| **Recordings in the right time zone** | Hikvision search and playback times are the recorder's own clock time, even with a trailing `Z`. 1.0.0 read them as UTC, so outside UTC every recording was hours out. Home Assistant's time zone is used, or set *Recorder time zone*. |
| **Works on Home Assistant 2026.10+** | On 2026.10 the original's camera entities failed to load (its open issue #2); the fork drops the `via_device` link that triggered it, so cameras are no longer grouped under the recorder. |
| **Person / vehicle detections** | The recorder's own smart search (AcuSense), with thumbnails, kept in a small index so a day is searched once. Recorders without it are noticed and left alone. |
| **PTZ tap-to-aim and presets** | `ptz_aim` points the camera at a spot in its picture or zooms in to a box; `ptz_presets` lists named presets and never offers the command numbers (94 is *Remote reboot*). |
| **Smoother replays on iPhone / iPad** | One playback stream per viewer: a clip you leave is stopped at once instead of idling and competing with the next. |
| **Events are opt-in** | The alert stream is one long-lived connection to the recorder; it only opens when you choose events. |
| **No sidebar panel, no injected script** | The card is a dashboard resource. The injected copy never registered in Firefox. |

<p align="center">
  <img src="docs/images/card-live.png" alt="The card in live view: one channel large, the rest as a strip below" width="480">
  &nbsp;
  <img src="docs/images/setup-dialog.png" alt="Adding an NVR from the Home Assistant UI" width="420">
</p>
<p align="center"><sub>The card in live view, and setup from the UI. Camera imagery is blurred here; it is not blurred in the integration.</sub></p>

## What you get

| | |
|---|---|
| **Live view** | One `camera` entity per channel, RTSP → HLS through Home Assistant's own stream engine. Works in the app, on the web, on Chromecast. |
| **Playback** | Scrub a day of recordings on a timeline and play any moment, straight from the NVR's disks. No local copy, no re-recording. |
| **Media browser** | Recordings appear under **Media → Hikvision NVR → camera → day**. |
| **Events** | Motion, line crossing, intrusion, tamper, video loss, face detection and more — pushed over ISAPI's alert stream, not polled. The integration asks the NVR which events each channel actually supports and creates exactly those, so nothing dead appears and nothing real is missed. |
| **NVR health** | Uptime, CPU, memory, per-disk usage, free space and health, online channel count, plus disk / network / illegal-login / recording-failure sensors. |
| **Camera health** | A connectivity sensor per channel, from the NVR's own per-channel probe — truer than an ICMP ping, and it works even when the cameras sit on the NVR's PoE subnet. |
| **REST API** | `/api/hikvision_nvr/…` for third-party mobile apps, using ordinary Home Assistant tokens. |
| **Detections** | Person and vehicle detections per channel and day, with thumbnails, for timelines (`/api/hikvision_nvr/{device}/{channel}/detections`). |
| **Services** | Search recordings, export a clip to MP4, PTZ move / aim / presets, enable notifications, reboot. |

## Install

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/deekay2153/ultimate-hikvision-nvr`,
   category **Integration**. (Using the original? Remove it first: same domain.)
2. Install **Ultimate Hikvision NVR**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Hikvision NVR**.

### Manual

Copy `custom_components/hikvision_nvr/` into your `config/custom_components/`
directory and restart Home Assistant.

### The card

Nothing to do. The integration ships its own card and adds it to the dashboard
resources on startup, so it is available on any dashboard:

Add it from **Add card → Hikvision** and pick everything from dropdowns — the
NVR, which cameras to show, whether it opens on live or history, live quality
and the grid width. No YAML, no entity ids to look up.

The equivalent YAML, if you prefer it:

```yaml
type: custom:hikvision-nvr-card
device: DS-7608NI-…      # optional, defaults to the first NVR
channels: [1, 2, 4]      # optional, defaults to all
default_mode: live       # or: playback
live_stream: 1           # 1 = main, 2 = sub
columns: 4
```

In **History**, the **Clip** dropdown sets how much video a click on the timeline
plays — and therefore how much **Download** saves, so the two never disagree.

The timeline zooms: **scroll** on it (or **pinch** on a touchscreen) to zoom
around the pointer. Once zoomed, move around with the **◀ ▶** buttons, by
**dragging**, or with the arrow keys; **Whole day** goes back out. Tick labels
get finer as you zoom in. All of it works on the day already loaded, so zooming
never waits on the NVR.

If the card does not appear right after an update, hard-refresh the browser
(Ctrl-Shift-R) — the frontend caches by version.

## Setup

| Field | Notes |
|---|---|
| Host | IP or hostname of the **NVR** (not a camera). |
| Username / password | A device account. Operator is enough; admin is only needed for `reboot`. |
| HTTP port | 80 by default, 443 with HTTPS. |
| RTSP port | 554 by default. |

On the NVR, make sure **Hikvision-CGI / ISAPI** is enabled
(*Configuration → System → Security → Authentication*) and that the account is
not locked out from earlier failed logins.

## Options

**Settings → Devices & Services → Hikvision NVR → Configure**

- **Channels to expose** — hide unused channels.
- **Events to expose** — which detections become binary sensors. Only what your
  device actually reports is offered, and unticking one removes its entities
  rather than leaving them behind. A capable NVR reports far more than most
  people want.
- **Live view stream** — main (full resolution) or sub (light, starts faster).
- **Snapshot stream** — sub stream keeps thumbnails cheap on large systems.
- **Recorder time zone** — leave empty when the recorder's clock is set to the
  same time zone as Home Assistant; otherwise its IANA name, e.g. `Europe/London`.

Nothing is ticked under **Events to expose** at first: playback, the timeline
and its person / vehicle markers need no events, and each event sensor keeps a
connection to the recorder open.

## Documentation

- [docs/API.md](docs/API.md) — the REST API, endpoint by endpoint, with examples.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how it is built, verified device
  behaviour, operations and troubleshooting.

## A note on H.265

If your channels record in H.265/HEVC, playback works in Safari, iOS and most
Android devices, but desktop Chrome and Firefox cannot decode HEVC in HLS. Set
the recording or sub-stream codec to **H.264** on the NVR for universal
playback, or put go2rtc in front to transcode. `export_recording` produces a
plain MP4 that plays everywhere either way.

**H.265+ (Hikvision "SmartCodec") freezes live video in Firefox** a few seconds
in, while Chrome, Edge and Safari carry on. If a camera's live picture freezes
in Firefox only, turn **H.265+** off for that camera's stream on the recorder
(plain H.265 is fine). It costs some disk: SmartCodec saves roughly 30-50 %.

## Motion sensors staying off

First, choose the events you want under **Configure → Events to expose**: none
are chosen at first.

A Hikvision trigger can record, notify, both, or neither — and "record only" is
a common factory default. A channel set that way fills the disk with motion
clips while Home Assistant never hears a thing, because only *Notify
Surveillance Center* pushes an event to the alert stream this integration
listens on.

Check with the service, which reports what it changed:

```yaml
action: hikvision_nvr.enable_notifications
response_variable: result      # {"changed": ["VMD-1", ...], "count": 8}
```

It only ever adds the notification; recording and every other linkage is left
exactly as it was. Narrow it with `event_type:` and `channel:` if you want.

## Branding

The mark in `brand/` is original artwork for this project, not the Hikvision
logo — that is Hikvision's trademark and not ours to redistribute. "Hikvision"
appears here only to say which hardware this integration talks to.

The icon on **Settings → Devices & Services** comes from
`custom_components/hikvision_nvr/brand/`. Home Assistant serves brand images
straight from any integration that has a `brand` directory, so nothing needs to
be published anywhere for it to appear. Only `icon.png` is required — Home
Assistant falls back through it for the `@2x` and dark variants.

To use your own artwork, edit `brand/icon.svg` and run `python brand/render.py`,
or drop your own PNGs into `custom_components/hikvision_nvr/brand/`.

Submitting to [home-assistant/brands](https://github.com/home-assistant/brands)
is therefore optional; it would only matter if this integration were ever
accepted into Home Assistant core. Assets and instructions for that are in
[`brand/home-assistant-brands/`](brand/home-assistant-brands/README.md).

## Contributing

Pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the
checks CI runs and the one structural rule (`isapi.py` never imports Home
Assistant). Report anything exploitable through
[SECURITY.md](SECURITY.md) rather than a public issue.

This project is not affiliated with or endorsed by Hikvision. Thanks to
[techmarkai](https://github.com/techmarkai) for the original integration.

## Support

If this saves you a trip to the recorder's own app, you can [buy me a coffee](https://www.buymeacoffee.com/deekay2153). Thank you!

## Licence

MIT — see [LICENSE](LICENSE).
