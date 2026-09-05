"""The APK has to carry the version of the release it ships in.

The phone compares the GitHub release tag against its own manifest version to
decide whether an update exists. While those were separate schemes - releases
at 4.11.x, the manifest at 1.3 - the comparison was true forever, so a phone
on the newest APK would have been offered an update every day and installing
it would not have changed the answer. Nobody hit that only because no APK had
ever been published.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "android"))
from set_version import MAX_PART, parse_tag, stamp, version_code  # noqa: E402


@pytest.mark.parametrize("tag,expected", [
    ("v4.11.3", (4, 11, 3)),
    ("4.11.3", (4, 11, 3)),
    ("V4.11.3", (4, 11, 3)),
    ("v5.0", (5, 0, 0)),
    ("v2", (2, 0, 0)),
    ("v1.2.3-beta", (1, 2, 3)),
])
def test_tags_are_read(tag, expected):
    assert parse_tag(tag) == expected


@pytest.mark.parametrize("tag", ["", "vNext", "release"])
def test_a_tag_that_is_not_a_version_is_refused(tag):
    with pytest.raises(ValueError):
        parse_tag(tag)


def test_version_codes_only_ever_go_up():
    order = ["v1.0.0", "v1.0.1", "v1.2.0", "v1.11.0", "v2.0.0", "v4.11.2",
             "v4.11.3", "v4.12.0", "v10.0.0"]
    codes = [version_code(parse_tag(t)) for t in order]
    assert codes == sorted(codes)
    assert len(set(codes)) == len(codes)


def test_a_code_that_would_break_the_ordering_is_refused():
    """1.100.0 would pack onto 2.0.0 and every later release would look older
    than one that came before it - an APK nobody could update."""
    with pytest.raises(ValueError):
        version_code((1, MAX_PART + 1, 0))
    with pytest.raises(ValueError):
        version_code((1, 0, MAX_PART + 1))


def test_it_beats_the_version_already_shipped():
    """versionCode must exceed whatever is in the repo, or a phone that
    somehow has that build could not be updated."""
    manifest = (Path(__file__).resolve().parent.parent
                / "android" / "AndroidManifest.xml").read_text(encoding="utf-8")
    import re

    current = int(re.search(r'android:versionCode="(\d+)"', manifest).group(1))
    assert version_code(parse_tag("v4.11.3")) > current


def test_the_manifest_is_stamped(tmp_path):
    manifest = tmp_path / "AndroidManifest.xml"
    manifest.write_text(
        '<manifest android:versionCode="4" android:versionName="1.3">\n'
        '  <uses-sdk android:minSdkVersion="23" />\n</manifest>\n',
        encoding="utf-8")

    name, code = stamp(manifest, "v4.11.3")

    assert (name, code) == ("4.11.3", 41103)
    out = manifest.read_text(encoding="utf-8")
    assert 'android:versionCode="41103"' in out
    assert 'android:versionName="4.11.3"' in out
    assert "minSdkVersion" in out          # nothing else was disturbed


def test_stamping_the_real_manifest_leaves_it_valid(tmp_path):
    source = (Path(__file__).resolve().parent.parent
              / "android" / "AndroidManifest.xml")
    copy = tmp_path / "AndroidManifest.xml"
    copy.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    stamp(copy, "v9.9.9")

    out = copy.read_text(encoding="utf-8")
    assert 'android:versionName="9.9.9"' in out
    assert 'android:versionCode="90909"' in out
    # the parts the APK cannot be built without
    assert "tw.lagscope.viewer" in out and "MainActivity" in out


def test_a_manifest_without_the_fields_is_an_error(tmp_path):
    manifest = tmp_path / "AndroidManifest.xml"
    manifest.write_text("<manifest/>", encoding="utf-8")
    with pytest.raises(ValueError):
        stamp(manifest, "v1.0.0")


def test_the_phone_would_stop_asking_after_installing():
    """The whole point: isNewer(tag, installed) has to become false."""
    name, _code = stamp_in_memory("v4.11.3")
    assert name == "4.11.3"          # identical to the tag it shipped in


def stamp_in_memory(tag):
    parts = parse_tag(tag)
    return ".".join(str(p) for p in parts), version_code(parts)
