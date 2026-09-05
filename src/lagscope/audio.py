"""Making a click, so the ear has something to compare the screen against.

Bluetooth audio latency is not a number any operating system will tell you.
Windows has no public API for the A2DP codec in use, and Android's
BluetoothCodecConfig needs a permission only system apps get - so the honest
options are to guess from a table of codecs, or to measure. This measures.

The method is the one television installers use for lip sync: show a flash and
play a click, let the person shift one against the other until the two land
together, and read the answer off the slider. The comparator is a human ear,
which sounds imprecise until you notice that a human ear is exactly the
instrument the answer is *for*. People notice audio/video mismatch from around
20-40 ms; the delay being measured here is usually 100-250 ms.

Playback deliberately avoids QtMultimedia. The project depends on
PySide6-Essentials, which does not ship it, and pulling in the full PySide6 to
play one click would add far more to the installer than this feature is worth.
A WAV is a header and some samples, and every desktop platform can already play
one:

    Windows   winsound, in the standard library, in-process
    macOS     afplay
    Linux     paplay / aplay / ffplay, whichever exists

Only the Windows path is in-process. Everywhere else a process is spawned per
click, and process startup then counts as part of "how late the sound was" -
tens of milliseconds of it. That is a real error in the measurement, so the
caller is told about it (see ``spawns_process``) rather than left to wonder.
"""

from __future__ import annotations

import io
import logging
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from typing import List, Optional

LOG = logging.getLogger(__name__)

SAMPLE_RATE = 44100
# Long enough to survive a lossy codec, short enough to be a "click" rather
# than a "beep": something with a smeared edge is hard to place in time.
DEFAULT_DURATION_MS = 12.0
# High enough to cut through, low enough that older ears still hear it well.
DEFAULT_FREQ_HZ = 2000.0
# Full scale would clip on some mixers and is louder than anyone wants in a
# headset held to the ear.
DEFAULT_AMPLITUDE = 0.5
# Ramping the first and last millisecond stops the speaker popping, which would
# be a second sound arriving at a different time from the one being measured.
FADE_MS = 1.0

_POSIX_PLAYERS = (
    # paplay first: on a PulseAudio/PipeWire desktop it is the shortest path to
    # the sink, and Bluetooth audio on Linux goes through one of those anyway.
    ("paplay", ()),
    ("aplay", ("-q",)),
    ("ffplay", ("-nodisp", "-autoexit", "-loglevel", "quiet")),
    ("afplay", ()),          # macOS
)


def click_wav(duration_ms: float = DEFAULT_DURATION_MS,
              freq_hz: float = DEFAULT_FREQ_HZ,
              amplitude: float = DEFAULT_AMPLITUDE,
              sample_rate: int = SAMPLE_RATE) -> bytes:
    """A complete mono 16-bit WAV file, in memory, containing one click."""
    duration_ms = max(1.0, float(duration_ms))
    amplitude = min(1.0, max(0.0, float(amplitude)))
    count = max(1, int(sample_rate * duration_ms / 1000.0))
    fade = max(1, int(sample_rate * FADE_MS / 1000.0))
    fade = min(fade, count // 2)

    peak = int(amplitude * 32767)
    samples: List[int] = []
    for i in range(count):
        value = math.sin(2.0 * math.pi * freq_hz * i / sample_rate)
        # Raised cosine in and out. A rectangular window would click twice.
        if fade > 0:
            if i < fade:
                value *= 0.5 - 0.5 * math.cos(math.pi * i / fade)
            elif i >= count - fade:
                remaining = count - 1 - i
                value *= 0.5 - 0.5 * math.cos(math.pi * remaining / fade)
        samples.append(int(round(value * peak)))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return buffer.getvalue()


def posix_player() -> Optional[List[str]]:
    """The command that will play a WAV file, or None if nothing can."""
    for name, args in _POSIX_PLAYERS:
        found = shutil.which(name)
        if found:
            return [found, *args]
    return None


def available() -> bool:
    """Whether a click can be played at all on this machine."""
    if sys.platform == "win32":
        try:
            import winsound  # noqa: F401
        except ImportError:
            return False
        return True
    return posix_player() is not None


def spawns_process() -> bool:
    """True when each click costs a process launch, which the answer includes.

    The caller shows this as a caveat. It is not a small effect - process
    startup is tens of milliseconds, and every one of them is indistinguishable
    from headset delay to the person doing the comparison.
    """
    return sys.platform != "win32"


class Clicker:
    """Plays the same short click over and over, as promptly as it can.

    The WAV is built once. On Windows the bytes are handed straight to the
    system, which is why that path is the accurate one; elsewhere they are
    written to a temporary file that a player process is pointed at.
    """

    def __init__(self, wav: Optional[bytes] = None) -> None:
        self._wav = wav if wav is not None else click_wav()
        self._path: Optional[str] = None
        self._player = None if sys.platform == "win32" else posix_player()
        self._processes: List[subprocess.Popen] = []
        # Why the last attempt failed, for the UI to show. Silently greying a
        # button out leaves someone staring at a dialog that does nothing and
        # no way to find out why.
        self.last_error: str = ""

    @property
    def wav(self) -> bytes:
        return self._wav

    def play(self) -> bool:
        """Start the click. Returns False if this machine cannot play it."""
        try:
            if sys.platform == "win32":
                return self._play_windows()
            return self._play_posix()
        except Exception as exc:
            LOG.exception("could not play calibration click")
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            return False

    def _wav_path(self) -> str:
        """The click on disk. Written once and reused for the whole session."""
        if self._path is None:
            handle, path = tempfile.mkstemp(prefix="lagscope-click-", suffix=".wav")
            with os.fdopen(handle, "wb") as out:
                out.write(self._wav)
            self._path = path
        return self._path

    def _play_windows(self) -> bool:
        try:
            import winsound
        except ImportError:
            self.last_error = "winsound is missing from this build"
            return False
        # From a file, not from memory. CPython refuses SND_MEMORY together
        # with SND_ASYNC outright - PC/winsound.c raises "Cannot play
        # asynchronously from memory", because an async call would return
        # while still holding a buffer it does not own. Playing synchronously
        # instead would block the UI thread on the audio device, which on a
        # Bluetooth headset is exactly the thing being measured. So the click
        # goes to a temporary file and Windows reads it from there.
        winsound.PlaySound(self._wav_path(),
                           winsound.SND_FILENAME | winsound.SND_ASYNC
                           | winsound.SND_NODEFAULT)
        return True

    def _play_posix(self) -> bool:
        if not self._player:
            self.last_error = "no audio player found (paplay / aplay / ffplay)"
            return False
        path = self._wav_path()
        self._reap()
        self._processes.append(subprocess.Popen(
            [*self._player, path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))
        return True

    def _reap(self) -> None:
        """Clear finished players so a long session does not collect zombies."""
        self._processes = [p for p in self._processes if p.poll() is None]

    def stop(self) -> None:
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
            return
        for process in self._processes:
            if process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    pass
        self._processes = []

    def close(self) -> None:
        self.stop()
        if self._path:
            try:
                os.unlink(self._path)
            except OSError:
                pass
            self._path = None
