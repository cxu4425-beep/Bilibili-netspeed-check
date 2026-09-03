import csv

from lagscope.models import LatencySample
from lagscope.recording import HEADER, CsvRecorder


def test_writes_a_header_once_and_appends_rows(tmp_path):
    path = tmp_path / "latency.csv"
    recorder = CsvRecorder(path)
    recorder.write(LatencySample(total_ms=1234.5, network_ms=42.0, stream_ms=1200.0,
                                 display_ms=33.0, method="hls-pdt", host="cdn"))
    recorder.write(LatencySample(ok=False, error="boom\nsecond line"))
    recorder.close()

    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0] == HEADER
    column = {name: index for index, name in enumerate(rows[0])}
    assert [rows[1][column[name]] for name in
            ("total_ms", "network_ms", "stream_ms", "display_ms")] == \
        ["1234.5", "42.0", "1200.0", "33.0"]
    assert rows[2][column["ok"]] == "0"
    assert "\n" not in rows[2][column["error"]]

    CsvRecorder(path).write(LatencySample(total_ms=1.0))
    assert sum(1 for row in csv.reader(path.open(encoding="utf-8")) if row[0] == "timestamp") == 1


def test_rotation_keeps_the_configured_number_of_backups(tmp_path):
    path = tmp_path / "latency.csv"
    recorder = CsvRecorder(path, backups=2)
    recorder.max_bytes = 400
    for index in range(200):
        recorder.write(LatencySample(total_ms=float(index)))
    recorder.close()

    names = sorted(p.name for p in tmp_path.iterdir())
    assert "latency.csv.1" in names and "latency.csv.2" in names
    assert "latency.csv.3" not in names


def test_a_file_written_by_an_older_version_is_moved_aside(tmp_path):
    """Appending new columns under an old header produces a file where the
    names and the values no longer line up, and nothing looks wrong until
    somebody tries to read it."""
    path = tmp_path / "latency.csv"
    path.write_text("timestamp,iso_time,total_ms,ok\n1,2,3,1\n", encoding="utf-8")

    recorder = CsvRecorder(path)
    recorder.write(LatencySample(total_ms=1.0, audio_ms=170.0))
    recorder.close()

    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0] == HEADER
    assert rows[1][rows[0].index("audio_ms")] == "170.0"
    assert (tmp_path / "latency.csv.1").exists()      # the old one is kept


def test_a_matching_header_is_appended_to_not_rotated(tmp_path):
    path = tmp_path / "latency.csv"
    CsvRecorder(path).write(LatencySample(total_ms=1.0))
    CsvRecorder(path).write(LatencySample(total_ms=2.0))
    assert not (tmp_path / "latency.csv.1").exists()
    assert len(list(csv.reader(path.open(encoding="utf-8")))) == 3
