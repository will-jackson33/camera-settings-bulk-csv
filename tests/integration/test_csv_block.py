"""The shared CSV block in the import: a settings file in either shape read into one structure and
written back as CCT's own file. The readable pair the export wrote goes round the trip whole, the
shapes Excel saves are told apart from their bytes, and every value a person could type is
normalised or refused the way the editor did."""

from __future__ import annotations

import csv
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.unit.camerasettings.fixtures import real_export_bytes, sample_bytes

from .support import BAT, run_block, run_code

ROUND_TRIP = ("$f = Read-Any $env:PSIN; if ($null -eq $f) { 'null'; exit 0 }; Write-Native $f $env:PSOUTFILE; "
              "$f.Format + '|' + $f.Order.Count")


def readable_pair(data: bytes, folder: Path) -> Path:
    """settings.csv and analytics.csv as the export writes them from CCT's own file."""
    (folder / "cct.csv").write_bytes(data)
    result = run_block("READABLE", {"PSCSV": str(folder / "cct.csv"), "PSREADABLE": str(folder / "settings.csv"),
                                    "PSANALYTICS": str(folder / "analytics.csv")}, script=BAT)
    assert result.returncode == 0, result.stderr
    return folder / "settings.csv"


def round_trip(path: Path) -> tuple[str, bytes | None]:
    out = path.with_name("native.csv")
    result: subprocess.CompletedProcess = run_code(["COLS", "CSV"], ROUND_TRIP, {"PSIN": str(path), "PSOUTFILE": str(out)})
    assert result.returncode == 0, result.stderr
    return result.stdout.strip(), (out.read_bytes() if out.exists() else None)


def rewrite(path: Path, delimiter: str, encoding: str, bom: bool) -> None:
    """The readable file as Excel would save it another way: another delimiter, another encoding."""
    rows = list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"))))
    text = io.StringIO()
    csv.writer(text, delimiter=delimiter, lineterminator="\r\n").writerows(rows)
    data = text.getvalue().encode(encoding)
    if bom:
        data = {"utf-8": b"\xef\xbb\xbf", "utf-16-le": b"\xff\xfe"}[encoding] + data
    path.write_bytes(data)


class CsvBlockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_cct_own_file_is_read_as_such_and_rewritten_byte_for_byte(self):
        native = self.folder / "cct.csv"
        native.write_bytes(sample_bytes())
        self.assertEqual(round_trip(native), ("cct|4", sample_bytes()))

    def test_the_readable_pair_goes_round_the_trip_whole(self):
        readable = readable_pair(sample_bytes(), self.folder)
        self.assertEqual(round_trip(readable), ("readable|4", sample_bytes()))

    def test_the_shapes_excel_saves_all_read(self):
        for delimiter, encoding, bom in ((",", "utf-8", False), (",", "cp1252", False), (";", "cp1252", False),
                                         ("\t", "utf-16-le", True), (",", "utf-8", True)):
            with self.subTest(delimiter=delimiter, encoding=encoding, bom=bom):
                readable = readable_pair(sample_bytes(), self.folder)
                rewrite(readable, delimiter, encoding, bom)
                self.assertEqual(round_trip(readable), ("readable|4", sample_bytes()))

    def test_settings_csv_alone_leaves_every_head_as_it_is(self):
        readable = readable_pair(sample_bytes(), self.folder)
        (self.folder / "analytics.csv").unlink()
        stdout, native = round_trip(readable)
        self.assertEqual(stdout, "readable|4")
        assert native is not None
        lines = native[2:].decode("utf-16-le").splitlines()
        self.assertEqual(lines[1], "AnalyticsHeader\tHead\t")
        self.assertEqual(sum(1 for ln in lines if ln.startswith("Analytics\t")), 0)

    def test_not_a_settings_file(self):
        for name, data in (("words.csv", b"hello there\r\n"), ("empty.csv", b""),
                           ("headers.csv", b"Name,Location\r\nx,y\r\n"), ("utf16.csv", b"\xff\xfe" + "Nope".encode("utf-16-le"))):
            with self.subTest(name=name):
                path = self.folder / name
                path.write_bytes(data)
                self.assertEqual(round_trip(path), ("null", None))

    def test_the_real_export_goes_round_the_trip_whole(self):
        data = real_export_bytes()
        if data is None:
            self.skipTest("no site export beside the scripts")
        readable = readable_pair(data, self.folder)
        stdout, native = round_trip(readable)
        self.assertTrue(stdout.startswith("readable|"), stdout)
        self.assertEqual(native, data)

    def test_values_are_normalised_or_refused_as_the_editor_did(self):
        code = ("$cases = @(@('CameraLedDisabled','TRUE'), @('Quality','21'), @('Resolution','1920x1080'), "
                "@('AnalyticsSceneMode','outdoor'), @('Encoding','h265'), @('SerialNumber','x''y'), "
                "@('IpAddress','10.020.3.1'), @('IpAddress','10.20.3.999'), @('TamperThreshold','0.5'), @('Hostname',''), "
                "@('VideoAnalyticsMode','UMD - unusual motion detection'), @('CameraMode','full feature'), "
                "@('CameraType','Purple'), @('ImageRate','0')); "
                "foreach ($c in $cases) { $r = Normalize $c[0] $c[1]; if ($r.Ok) { $c[0] + '=' + $r.Value } else { $c[0] + '!' + $r.Reason } }")
        result = run_code(["COLS", "CSV"], code, {})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "CameraLedDisabled=True",
            "Quality!Quality must be at most 20, not 21",
            "Resolution=1920 x 1080",
            "AnalyticsSceneMode=0",
            "Encoding=H265",
            "SerialNumber!SerialNumber cannot contain the ' character - CCT uses it to wrap the value",
            "IpAddress=10.20.3.1",
            "IpAddress!IpAddress takes an address like 10.20.3.128, not '10.20.3.999'",
            "TamperThreshold=0.5",
            "Hostname=",
            "VideoAnalyticsMode=1",
            "CameraMode=Full Feature",
            "CameraType!CameraType takes one of Colour (0), Black and White (1), Day and Night (2), Thermal (3), not 'Purple'",
            "ImageRate!ImageRate must be at least 1, not 0",
        ])


if __name__ == "__main__":
    unittest.main()
