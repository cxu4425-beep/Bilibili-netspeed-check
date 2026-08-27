"""Per-user configuration.

The config lives in the current user's own config directory, so several people
can use the same machine (or the same portable copy of the .exe) without
sharing settings. Nothing here requires a Bilibili account or a cookie.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Any, Optional

from . import APP_ID, APP_NAME
from .probes.video import parse_video_id, parse_video_page

CONFIG_VERSION = 1

_ROOM_URL_RE = re.compile(r"live\.bilibili\.com/(?:blanc/|h5/)?(\d+)", re.IGNORECASE)
_DIGITS_RE = re.compile(r"^\d{1,12}$")


def app_config_dir() -> Path:
    """Return (and create) this user's config directory."""
    override = os.environ.get("BILI_LATENCY_CONFIG_DIR")
    if override:
        base = Path(override).expanduser()
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".config") / APP_ID
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return app_config_dir() / "config.json"


def title_memory_path() -> Path:
    """Where learned "window title -> room/video" pairs are kept."""
    return app_config_dir() / "titles.json"


def log_dir() -> Path:
    path = app_config_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_room_id(text: str) -> str:
    """Accept a room id, a live URL, or a pasted address bar; return the id."""
    text = (text or "").strip()
    if not text:
        return ""
    match = _ROOM_URL_RE.search(text)
    if match:
        return match.group(1)
    if _DIGITS_RE.match(text):
        return text
    return ""


@dataclass
class OverlayConfig:
    enabled: bool = True
    # "free"    - wherever you dragged it
    # "screen"  - pinned to a corner of a chosen screen
    # "window"  - follows the Bilibili window (Windows only, falls back to screen)
    anchor_mode: str = "free"
    x: int = 80
    y: int = 80
    screen_name: str = ""
    corner: str = "top-right"      # top-left | top-right | bottom-left | bottom-right
    offset_x: int = 24
    offset_y: int = 24
    opacity: float = 0.88
    scale: float = 1.0
    always_on_top: bool = True
    click_through: bool = False
    locked: bool = False
    compact: bool = False
    show_breakdown: bool = True
    show_sparkline: bool = True
    show_stats: bool = True
    theme: str = "dark"            # dark | light | pink
    follow_window_keyword: str = "哔哩哔哩"


@dataclass
class TrayConfig:
    enabled: bool = True
    show_value_in_icon: bool = True


@dataclass
class ProbeConfig:
    interval_ms: int = 2000
    timeout_ms: int = 4000
    playurl_refresh_s: int = 240
    rtt_host: str = "api.live.bilibili.com"
    rtt_port: int = 443
    prefer_hls: bool = True
    player_buffer_segments: float = 1.0
    max_backoff_multiplier: int = 8


@dataclass
class DisplayConfig:
    # Frames the compositor keeps in flight before a frame is lit up.
    frames_in_flight: float = 2.0
    # Panel input lag you measured yourself (e.g. from a review site), in ms.
    manual_offset_ms: float = 0.0
    include_in_total: bool = True


@dataclass
class RecordingConfig:
    csv_enabled: bool = False
    csv_max_bytes: int = 8 * 1024 * 1024
    csv_backups: int = 3


@dataclass
class DetectConfig:
    """Automatic detection of what you are watching (every source optional)."""

    enabled: bool = True
    use_client: bool = True       # read the official desktop client's own data folder
    use_history: bool = True      # newest bilibili.com URL in the browser history
    use_titles: bool = True       # match it against open window titles (Windows)
    use_bridge: bool = False      # accept reports from the companion userscript
    use_clipboard: bool = True    # a link copied from the desktop client's share menu
    remember_titles: bool = True  # learn which window title belongs to which page
    follow_videos: bool = True    # follow video pages too, not only live rooms
    # Extra folders to look in when the client is installed somewhere unusual.
    client_dirs: list = field(default_factory=list)
    history_window_min: int = 30
    poll_interval_s: int = 5
    bridge_port: int = 23124
    bridge_timeout_s: int = 120


@dataclass
class ThresholdConfig:
    good_ms: float = 2000.0
    warn_ms: float = 5000.0


@dataclass
class Config:
    version: int = CONFIG_VERSION
    language: str = "auto"          # auto | zh_CN | zh_TW | en
    room_id: str = ""
    video_id: str = ""              # BV id (or avNNN), used when manual_kind is "video"
    video_page: int = 1             # which part (P) of that video
    manual_kind: str = "live"       # what to watch when auto-detection is off or idle
    sample_window: int = 180
    autostart: bool = False
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    tray: TrayConfig = field(default_factory=TrayConfig)
    probe: ProbeConfig = field(default_factory=ProbeConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    detect: DetectConfig = field(default_factory=DetectConfig)

    # ---------------------------------------------------------------- loading
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        return _build(cls, data or {})

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        path = path or config_path()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return cls()
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            # A corrupt config must never stop the app from starting.
            _quarantine(path)
            return cls()
        if not isinstance(data, dict):
            _quarantine(path)
            return cls()
        return cls.from_dict(data)

    def save(self, path: Optional[Path] = None) -> None:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        # Atomic write: a crash mid-save must not truncate the config.
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp"
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_name = handle.name
        os.replace(tmp_name, path)

    def sanitized(self) -> "Config":
        """Clamp every value into a range the UI and probes can survive."""
        self.probe.interval_ms = int(_clamp(self.probe.interval_ms, 500, 60_000))
        self.probe.timeout_ms = int(_clamp(self.probe.timeout_ms, 1000, 30_000))
        self.probe.playurl_refresh_s = int(_clamp(self.probe.playurl_refresh_s, 30, 3600))
        self.probe.rtt_port = int(_clamp(self.probe.rtt_port, 1, 65535))
        self.probe.player_buffer_segments = _clamp(self.probe.player_buffer_segments, 0.0, 10.0)
        self.probe.max_backoff_multiplier = int(_clamp(self.probe.max_backoff_multiplier, 1, 60))
        self.overlay.opacity = _clamp(self.overlay.opacity, 0.2, 1.0)
        self.overlay.scale = _clamp(self.overlay.scale, 0.6, 3.0)
        self.sample_window = int(_clamp(self.sample_window, 20, 5000))
        self.display.frames_in_flight = _clamp(self.display.frames_in_flight, 0.0, 6.0)
        self.display.manual_offset_ms = _clamp(self.display.manual_offset_ms, 0.0, 500.0)
        self.thresholds.good_ms = _clamp(self.thresholds.good_ms, 10.0, 600_000.0)
        self.thresholds.warn_ms = _clamp(self.thresholds.warn_ms, self.thresholds.good_ms, 600_000.0)
        if self.overlay.anchor_mode not in ("free", "screen", "window"):
            self.overlay.anchor_mode = "free"
        if self.overlay.corner not in ("top-left", "top-right", "bottom-left", "bottom-right"):
            self.overlay.corner = "top-right"
        if self.overlay.theme not in ("dark", "light", "pink"):
            self.overlay.theme = "dark"
        if self.language not in ("auto", "zh_CN", "zh_TW", "en"):
            self.language = "auto"
        if not isinstance(self.detect.client_dirs, list):
            self.detect.client_dirs = []
        self.detect.client_dirs = [str(path) for path in self.detect.client_dirs if str(path).strip()]
        self.detect.history_window_min = int(_clamp(self.detect.history_window_min, 1, 1440))
        self.detect.poll_interval_s = int(_clamp(self.detect.poll_interval_s, 2, 300))
        self.detect.bridge_port = int(_clamp(self.detect.bridge_port, 1024, 65535))
        self.detect.bridge_timeout_s = int(_clamp(self.detect.bridge_timeout_s, 10, 3600))
        if self.manual_kind not in ("live", "video"):
            self.manual_kind = "live"
        self.room_id = parse_room_id(self.room_id)
        # A pasted URL carries its own part number; keep it.
        pasted_page = parse_video_page(self.video_id)
        self.video_id = parse_video_id(self.video_id)
        if pasted_page > 1:
            self.video_page = pasted_page
        self.video_page = int(_clamp(self.video_page, 1, 10_000))
        self.version = CONFIG_VERSION
        return self


def _clamp(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def _quarantine(path: Path) -> None:
    try:
        path.replace(path.with_suffix(path.suffix + ".broken"))
    except OSError:
        pass


def _build(cls: type, data: dict[str, Any]) -> Any:
    """Instantiate a dataclass from a dict, ignoring unknown keys.

    ``from __future__ import annotations`` makes every field type a string, so
    nested sections are resolved through the explicit ``_NESTED`` table.
    """
    kwargs: dict[str, Any] = {}
    known = {info.name for info in fields(cls)}
    for name, raw in data.items():
        if name not in known:
            continue
        nested_cls = _nested_dataclass(cls, name)
        if nested_cls is not None:
            if isinstance(raw, dict):
                kwargs[name] = _build(nested_cls, raw)
            continue
        kwargs[name] = raw
    return cls(**kwargs)


_NESTED = {
    "overlay": OverlayConfig,
    "tray": TrayConfig,
    "probe": ProbeConfig,
    "display": DisplayConfig,
    "recording": RecordingConfig,
    "thresholds": ThresholdConfig,
    "detect": DetectConfig,
}


def _nested_dataclass(cls: type, name: str) -> Optional[type]:
    if cls is Config:
        return _NESTED.get(name)
    return None
