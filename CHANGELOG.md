# Changelog

Versioning is [semantic](https://semver.org/): the minor version moves for
features, the patch version for fixes. `manifest.json` carries the version HACS
installs, and the frontend cache-busts on it — so an upgrade always ships a
matching card.

## 1.2.0

- **Replays have sound.** Cameras that record G.711, AAC or PCM audio now play
  it in replays and saved clips: the sound is re-encoded to AAC while the video
  is still copied untouched. Cameras with audio off, or a codec ffmpeg cannot
  decode reliably (G.722.1, G.726), stay silent as before. iPhone / iPad
  replays go through Home Assistant's stream route and stay silent.

## 1.1.0 — fork: Ultimate Hikvision NVR

A fork of [techmarkai/hikvision-nvr-ha](https://github.com/techmarkai/hikvision-nvr-ha)
1.0.0, with the fixes from running it daily on a real recorder. Same domain
(`hikvision_nvr`), so it replaces the original in place.

- **Recordings line up in local time.** Hikvision search and playback times
  are the recorder's own clock time, even with a trailing `Z`; 1.0.0 read them
  as UTC, so every recording was hours out outside UTC. Home Assistant's time
  zone is used, or set the new *Recorder time zone* option.
- **Works on Home Assistant 2026.10+.** The original's camera entities failed
  to load on 2026.10 (its open issue #2); the fork drops the `via_device`
  link that triggered it. Cameras are no longer grouped under the recorder.
- **Person / vehicle detections** for the timeline: the recorder's own smart
  search, with thumbnails, kept in a small index so a day is searched once
  (`/api/hikvision_nvr/{device}/{channel}/detections`, `.../picture`,
  `.../thumb`).
  A recorder without that search (no AcuSense, older firmware) is noticed
  once, logged once, and answered with an empty list and `supported: false`
  instead of an error; the timeline then shows recordings without markers.
- **Smoother replays on iPhone / iPad.** One playback stream per viewer: the
  clip a viewer leaves is stopped at once instead of idling for minutes and
  competing with the next one (`client=` and `stop=1` on the playback view).
- **Events are opt-in.** The event stream (one long-lived connection to the
  recorder) and the notification check only run when events are chosen in the
  options. Playback and the timeline need none.
- **No sidebar panel, no injected script.** The card is added as a dashboard
  resource; the injected copy ran before Firefox's custom element support was
  ready and never registered.
- **PTZ tap-to-aim and preset list.** `hikvision_nvr.ptz_aim` points a PTZ at
  a spot in its picture or zooms in to a box (3D positioning);
  `hikvision_nvr.ptz_presets` returns the presets someone has named. Unnamed
  slots are left out (the camera reports all of them as in use), and so are
  the numbers Hikvision uses as commands -- 94 is *Remote reboot*.
- **Several recorders, several time zones.** Each recorder keeps its own time
  zone, detection lists and thumbnails.
- **Upgrading from the original keeps motion sensors working.** An entry that
  never saved its options still listens for events, as before.
- **Busy days are not cut short.** When one search returns its maximum, the
  stretch is asked again in halves instead of being stored with a gap.
- The background detection pass starts with the first detections request, so
  installs that never use the timeline never search.
- The recorder device no longer carries its MAC address, which made Home
  Assistant merge it into other Hikvision integrations' devices.

## 1.0.0 — first release

- **Live view** through Home Assistant's own camera element, which negotiates
  WebRTC via go2rtc: a decoding frame in about a second on the reference
  device, against roughly three to five for an HLS URL. HLS remains as a
  fallback and is only fetched if the WebRTC path is unavailable or stays
  black.
- **Playback** on a zoomable timeline, straight from the NVR's disks. Zoom and
  pan work on the day already loaded, so neither waits on the device. History
  plays as a fragmented MP4 in a plain `<video>`, which starts sooner than HLS
  and seeks natively.
- **Downloads and exports** from the NVR's bulk endpoint rather than its
  playback RTSP, which the device paces at real time — sixty seconds of video
  in about four and a half seconds against a sixty second floor — trimmed to
  the range asked for.
- **Events** pushed over ISAPI's alert stream rather than polled, created from
  the device's own capability declaration and switchable per type, so a capable
  NVR does not force fifty entities on anyone.
- **Live audio** where the channel actually has a microphone. G.711 passes
  through untouched.
- **Health**: uptime, CPU, memory, per-disk usage, free space and status, and
  per-channel connectivity from the NVR's own probe rather than an ICMP ping.
  A storage alarm re-reads the disks immediately, because an intermittent fault
  can begin and end between two polls.
- **Card, sidebar panel and REST API**, all registered on install — no Lovelace
  resource to add and no YAML to write.
- **Services**: search recordings, export to MP4, PTZ, reboot, and
  `enable_notifications` for the condition that makes motion sensors sit
  silently off — a detection the NVR records but never reports. That one has a
  preview mode, only ever adds the missing linkage, and is proven idempotent
  and strictly scoped against real hardware.
