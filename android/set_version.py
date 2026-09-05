"""Stamp the release version onto the APK before it is built.

The phone decides whether an update exists by comparing the GitHub release
tag against its own manifest version:

    Updater.isNewer(release.version, versionName())

Those were two unrelated numbering schemes - releases at 4.11.x, the manifest
at 1.3 - so the comparison was 4.11.3 against 1.3, true forever. A phone
running the newest APK would have been told there was an update available
every single day, and installing it would not have changed the answer.

So the APK carries the version of the release it ships in. After installing
from v4.11.3 the manifest says 4.11.3, the comparison is against itself, and
the answer is no.

versionCode has to be an integer that only ever goes up, so it is packed from
the same three parts. Minor and patch below 100 keeps that ordering true, and
the check below refuses anything that would break it rather than shipping an
APK that silently cannot be updated.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MAX_PART = 99


def parse_tag(tag: str) -> tuple:
    """``v4.11.3`` -> ``(4, 11, 3)``. Missing parts count as zero."""
    text = (tag or "").strip()
    if text[:1] in ("v", "V"):
        text = text[1:]
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", text)
    if not match:
        raise ValueError(f"not a version tag: {tag!r}")
    return tuple(int(part or 0) for part in match.groups())


def version_code(parts: tuple) -> int:
    """A single ascending integer, packed from major/minor/patch."""
    major, minor, patch = parts
    if minor > MAX_PART or patch > MAX_PART:
        # Packing would carry into the next field and the ordering would
        # break - 1.100.0 would land on top of 2.0.0.
        raise ValueError(
            f"minor and patch must be <= {MAX_PART} to stay ordered: {parts}")
    return major * 10_000 + minor * 100 + patch


def stamp(manifest: Path, tag: str) -> tuple:
    """Rewrite the manifest in place. Returns ``(name, code)``."""
    parts = parse_tag(tag)
    name = ".".join(str(part) for part in parts)
    code = version_code(parts)

    text = manifest.read_text(encoding="utf-8")
    text, n_code = re.subn(r'android:versionCode="\d+"',
                           f'android:versionCode="{code}"', text, count=1)
    text, n_name = re.subn(r'android:versionName="[^"]*"',
                           f'android:versionName="{name}"', text, count=1)
    if not (n_code and n_name):
        raise ValueError("versionCode/versionName not found in the manifest")
    manifest.write_text(text, encoding="utf-8")
    return name, code


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: set_version.py <AndroidManifest.xml> <tag>")
    stamped_name, stamped_code = stamp(Path(sys.argv[1]), sys.argv[2])
    print(f"versionName={stamped_name} versionCode={stamped_code}")
