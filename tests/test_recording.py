import csv

from bili_latency.models import LatencySample
from bili_latency.recording import HEADER, CsvRecorder


def test_writes_a_header_once_and_appends_rows(tmp_path):
    path = tmp_path / "latency.csv"
    recorder = CsvRecorder(path)
    recorder.write(LatencySample(total_ms=1234.5, network_ms=42.0, stream_ms=1200.0,
                                 display_ms=33.0, method="hls-pdt", host="cdn"))
    recorder.write(LatencySample(ok=False, error="boom\nsecond line"))
    recorder.close()

    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0] == HEADER
    assert rows[1][2:6] == ["1234.5", "42.0", "1200.0", "33.0"]
    assert rows[2][6] == "0"
    assert "\n" not in rows[2][10]

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
