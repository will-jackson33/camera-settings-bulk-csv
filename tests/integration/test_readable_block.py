"""The readable writer in the export: CCT's file becomes settings.csv, one comma-separated row per
camera, and analytics.csv, one row per head with the coded values as words. Run on the built
fixture always, and on the newest real export beside the scripts when there is one."""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
from pathlib import Path

import camerasettings_columns as columns
import camerasettings_csvfile as csvfile

from tests.unit.camerasettings.fixtures import real_export_bytes, sample_bytes

from .support import run_block

DEVICE_NAMES = [c.name for c in columns.DEVICE_COLUMNS[1:]]
ANALYTICS_NAMES = ["MacAddress", "Name", "IpAddress", "Head"] + [c.name for c in columns.ANALYTICS_COLUMNS[2:-1]]


def read_csv(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf", f"{path.name} does not start with the UTF-8 byte-order mark"
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""), f"{path.name} is not CRLF throughout"
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def convert(data: bytes) -> tuple[str, list[dict[str, str]], list[dict[str, str]]]:
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        (stage / "cct.csv").write_bytes(data)
        result = run_block("READABLE", {"PSCSV": str(stage / "cct.csv"), "PSREADABLE": str(stage / "settings.csv"),
                                        "PSANALYTICS": str(stage / "analytics.csv")})
        assert result.returncode == 0, result.stderr
        return result.stdout.strip(), read_csv(stage / "settings.csv"), read_csv(stage / "analytics.csv")


class ReadableBlockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.counts, cls.cameras, cls.heads = convert(sample_bytes())

    def test_counts_returned_to_cmd(self):
        self.assertEqual(self.counts, "4|6")

    def test_one_row_per_camera_in_cct_column_order_without_cct_quoting(self):
        self.assertEqual(list(self.cameras[0].keys()), DEVICE_NAMES)
        self.assertEqual([c["IpAddress"] for c in self.cameras], ["10.20.19.128", "10.20.19.131", "10.20.19.132", "10.20.3.130"])
        first = self.cameras[0]
        self.assertEqual(first["Name"], "acc/C1061 - Loading dock")
        self.assertEqual(first["SerialNumber"], "100000001")
        self.assertEqual(first["FirmwareVersion"], "5.20.0.24")
        self.assertEqual(first["Resolution"], "2592 x 1944")
        self.assertEqual(first["AdminPassword"], "")

    def test_a_name_holding_commas_survives(self):
        self.assertEqual(self.cameras[2]["Name"], "acc/C1090, C1091, C1092 - Multisensor")

    def test_one_row_per_head_with_words_for_the_codes(self):
        self.assertEqual(list(self.heads[0].keys()), ANALYTICS_NAMES)
        multisensor = [h for h in self.heads if h["MacAddress"] == "00-18-85-00-00-03"]
        self.assertEqual([h["Head"] for h in multisensor], ["1", "2", "3"])
        self.assertEqual(multisensor[0]["Name"], "acc/C1090, C1091, C1092 - Multisensor")
        self.assertEqual(multisensor[0]["IpAddress"], "10.20.19.132")
        self.assertEqual(multisensor[0]["AnalyticsSceneMode"], "Outdoor")
        self.assertEqual(multisensor[0]["VideoAnalyticsMode"], "VAL - video analytics")
        self.assertEqual(multisensor[0]["CameraType"], "")
        self.assertEqual(multisensor[0]["TamperSensitivity"], "8")

    def test_the_real_export_converts_whole(self):
        data = real_export_bytes()
        if data is None:
            self.skipTest("no site export beside the scripts")
        settings = csvfile.camerasettings_csvfile_parse(data)
        counts, cameras, heads = convert(data)
        self.assertEqual(counts, f"{len(settings.cameras)}|{sum(len(c.analytics) for c in settings.cameras)}")
        self.assertEqual(len(cameras), len(settings.cameras))
        for row, camera in zip(cameras, settings.cameras, strict=True):
            self.assertEqual(row["MacAddress"], settings.mac(camera))
            self.assertEqual(row["Name"], settings.value(camera, "Name"))
            self.assertEqual(row["SerialNumber"], settings.value(camera, "SerialNumber"))


if __name__ == "__main__":
    unittest.main()
