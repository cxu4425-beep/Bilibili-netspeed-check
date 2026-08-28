"""Start-with-the-system support.

Windows uses the per-user Run registry key, Linux an XDG autostart .desktop
file, macOS a LaunchAgent plist. Everything is per user - nothing is written
outside the current account, so several people on one PC keep their own choice.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from . import APP_ID, APP_NAME

LOG = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    """Command that starts this app the same way it is running now."""
    if getattr(sys, "frozen", False):  # PyInstaller build
        return f'"{sys.executable}"'
    script = Path(sys.argv[0]).resolve()
    if script.suffix.lower() == ".py":
        return f'"{sys.executable}" "{script}"'
    return f'"{sys.executable}" -m lagscope'


def is_supported() -> bool:
    return sys.platform.startswith(("win", "linux", "darwin"))


# ---------------------------------------------------------------------- win32
def _win_set(enabled: bool) -> bool:
    import winreg  # local import: Windows only

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError as exc:
        LOG.warning("autostart registry write failed: %s", exc)
        return False


def _win_get() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------- linux
def _linux_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / f"{APP_ID}.desktop"


def _linux_set(enabled: bool) -> bool:
    path = _linux_path()
    try:
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={APP_NAME}\n"
                f"Exec={launch_command()}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
        else:
            path.unlink(missing_ok=True)
        return True
    except OSError as exc:
        LOG.warning("autostart desktop file failed: %s", exc)
        return False


# ---------------------------------------------------------------------- macOS
def _mac_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"com.{APP_ID}.plist"


def _mac_set(enabled: bool) -> bool:
    path = _mac_path()
    try:
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            command = launch_command().replace('"', "")
            arguments = "".join(f"        <string>{part}</string>\n" for part in command.split(" ") if part)
            path.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0">\n'
                "<dict>\n"
                "    <key>Label</key>\n"
                f"    <string>com.{APP_ID}</string>\n"
                "    <key>ProgramArguments</key>\n"
                "    <array>\n"
                f"{arguments}"
                "    </array>\n"
                "    <key>RunAtLoad</key>\n"
                "    <true/>\n"
                "</dict>\n"
                "</plist>\n",
                encoding="utf-8",
            )
        else:
            path.unlink(missing_ok=True)
        return True
    except OSError as exc:
        LOG.warning("autostart plist failed: %s", exc)
        return False


# --------------------------------------------------------------------- public
def set_autostart(enabled: bool) -> bool:
    """Enable or disable autostart; returns True when the change was applied."""
    if sys.platform.startswith("win"):
        return _win_set(enabled)
    if sys.platform.startswith("linux"):
        return _linux_set(enabled)
    if sys.platform == "darwin":
        return _mac_set(enabled)
    return False


def get_autostart() -> Optional[bool]:
    """Current autostart state, or None when the platform is unsupported."""
    if sys.platform.startswith("win"):
        return _win_get()
    if sys.platform.startswith("linux"):
        return _linux_path().exists()
    if sys.platform == "darwin":
        return _mac_path().exists()
    return None
