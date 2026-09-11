"""The report block against a fabricated staging folder: three subnets that ran, one skipped, one
that ran past CCT's budget, a camera with bad credentials, a candidate CCT never mentioned, and a
console log that already held an older run before this one started."""
import datetime
import os
import tempfile
import unittest
from pathlib import Path

from .support import CCT_LOG_DIR, run_block, today_log_name, utf16_lines

HEADER = ["DeviceHeader\tMacAddress\tName\tLocation\tSerialNumber\tFirmwareVersion\tModel\tManufacturer"
          "\tA\tB\tC\tIpAddress\tSubnetMask",
          "AnalyticsHeader\tMacAddress\tAnalyticsEnabled"]


def device_rows(ip: str, name: str, mac: str) -> list[str]:
    return [f'Device\t{mac}\t"{name}"\t"Loc"\t\'SN\'\t"1.0"\tH4A\tAvigilon\tx\ty\tz\t{ip}\t255.255.255.0',
            f"Analytics\t{mac}\tTrue"]


def write_utf16(path: Path, lines: list[str]) -> None:
    path.write_bytes(b"\xff\xfe" + ("\r\n".join(lines) + "\r\n").encode("utf-16-le"))


class ReportBlockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stage = Path(self.tmp.name) / "stage"
        (self.stage / "subnets").mkdir(parents=True)
        self.appdata = Path(self.tmp.name) / "appdata"
        log_dir = self.appdata / CCT_LOG_DIR
        log_dir.mkdir(parents=True)

        # An older run today, already in CCT's log before this run's mark was taken. The mark
        # carries the path as Get-ChildItem reports it: the long form, never an 8.3 short name.
        log = log_dir / today_log_name()
        before = "10.20.1.99      LoggedIn            Old camera from an earlier run\n"
        log.write_text(before, encoding="utf-8")
        (self.stage / "logmark.txt").write_text(f"{len(before.encode('utf-8'))}|{os.path.realpath(log)}\n")
        with log.open("a", encoding="utf-8") as f:
            f.write("Start adding devices ...\n"
                    "10.20.3.5       LoggedIn            Cam A\n"
                    "\x1b[37m10.20.3.6       \x1b[32mLoggedIn            \x1b[33mCam B\x1b[0m\n"
                    "10.20.7.9       LoggedIn            Cam C\n"
                    "10.20.7.10      InvalidCredentials  \n")

        write_utf16(self.stage / "subnets" / "10.20.3.1.csv",
                    HEADER + device_rows("10.20.3.5", "Cam A", "00-18-85-00-00-01")
                    + device_rows("10.20.3.6", "Cam B", "00-18-85-00-00-02"))
        write_utf16(self.stage / "subnets" / "10.20.7.0.csv",
                    HEADER + device_rows("10.20.7.9", "Cam C", "00-18-85-00-00-03"))
        (self.stage / "sweep.txt").write_text("10.20.3.1 10.20.3.255 12 9\n"
                                              "10.20.5.0 10.20.5.255 3 0\n"
                                              "10.20.7.0 10.20.7.255 40 38\n"
                                              "10.20.9.0 10.20.9.255 5 2\n")
        (self.stage / "runlist.txt").write_text("10.20.3.1 10.20.3.255\n"
                                                "10.20.7.0 10.20.7.255\n"
                                                "10.20.9.0 10.20.9.255\n")
        (self.stage / "runs.txt").write_text("10.20.3.1-10.20.3.255|0|10:00:00.00|10:00:41.10\n"
                                             "10.20.7.0-10.20.7.255|6|10:00:42.00|10:01:30.00\n"
                                             "10.20.9.0-10.20.9.255|0|23:59:10.00| 0:01:16.00\n")
        (self.stage / "candidates.txt").write_text("10.20.3.5\n10.20.3.6\n10.20.3.77\n10.20.7.9\n"
                                                   "10.20.7.10\n10.20.9.1\n10.20.9.2\n")
        started = datetime.datetime.now() - datetime.timedelta(minutes=1)
        self.env = {
            "PSOUT": str(self.stage), "PSCSV": str(self.stage / "settings.csv"),
            "PSRPT": str(self.stage / "camera.log"), "RUNSTART": started.strftime("%Y-%m-%d %H:%M:%S"),
            "SITE": "Test Site", "IPRANGE": "10.20.3.1-10.20.9.255", "ADDRCOUNT": "1791",
            "ANSWERED": "60", "CANDS": "49", "RUNCOUNT": "3", "LOCALAPPDATA": str(self.appdata),
        }
        self.result = run_block("RPT", self.env)
        self.report = (self.stage / "camera.log").read_text(encoding="cp1252")

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts_returned_to_cmd(self):
        self.assertEqual(self.result.stdout.strip(), "1|3|1|0|2", self.result.stderr)

    def test_settings_csv_is_one_header_block_then_every_row_in_subnet_order(self):
        lines = utf16_lines(self.stage / "settings.csv")
        self.assertEqual(lines[:2], HEADER)
        self.assertEqual([ln.split("\t")[0] for ln in lines[2:]], ["Device", "Analytics"] * 3)
        self.assertEqual([ln.split("\t")[11] for ln in lines[2:] if ln.startswith("Device")],
                         ["10.20.3.5", "10.20.3.6", "10.20.7.9"])

    def test_every_subnet_is_accounted_for(self):
        self.assertIn("10.20.3.1-10.20.3.255              12     9        2   SUCCESS  (41 s)", self.report)
        self.assertIn("10.20.5.0-10.20.5.255               3     0        -   skipped - no web port open",
                      self.report)
        self.assertIn("10.20.7.0-10.20.7.255              40    38        1   "
                      "PARTIAL - at least one camera failed  (48 s)", self.report)
        self.assertIn("INCOMPLETE - CCT ran out of time at 126 s and left addresses unchecked. "
                      "Re-run as 10.20.9.0-10.20.9.127 and 10.20.9.128-10.20.9.255", self.report)
        self.assertIn("Subnets run        : 3  -  1 exported, 0 had no camera, 2 need a re-run", self.report)

    def test_rerun_list_names_the_problem_subnets_only(self):
        block = self.report.split("RE-RUN THESE SUBNETS")[1].split("\n\n")[0]
        self.assertIn("10.20.7.0-10.20.7.255", block)
        self.assertIn("10.20.9.0-10.20.9.255", block)
        self.assertNotIn("10.20.3.1", block)

    def test_only_this_runs_console_lines_count(self):
        self.assertIn("Logged in          : 3", self.report)
        self.assertNotIn("Old camera", self.report)
        console = (self.stage / "console.log").read_text(encoding="cp1252")
        self.assertNotIn("Old camera", console)
        self.assertIn("Cam C", console)

    def test_bad_credentials_and_unrecognised_candidates_are_listed(self):
        self.assertIn("10.20.7.10      InvalidCredentials", self.report)
        self.assertIn("Needs attention    : 1", self.report)
        tail = self.report.split("but CCT reported no camera there")[1]
        self.assertIn("  10.20.3.77", tail)
        self.assertIn("  10.20.9.1", tail)
        self.assertNotIn("  10.20.3.5\n", tail)

    def test_staging_scratch_files_are_gone(self):
        for name in ("logmark.txt", "sweep.txt", "runlist.txt", "runs.txt", "candidates.txt"):
            self.assertFalse((self.stage / name).exists(), name)
        self.assertTrue((self.stage / "subnets" / "10.20.3.1.csv").exists())


class ReportBlockWithNothingTest(unittest.TestCase):
    def test_no_runs_and_no_csv_still_writes_a_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "stage"
            (stage / "subnets").mkdir(parents=True)
            for name in ("logmark.txt", "sweep.txt", "runlist.txt", "candidates.txt"):
                (stage / name).write_text("")
            env = {"PSOUT": str(stage), "PSCSV": str(stage / "settings.csv"),
                   "PSRPT": str(stage / "camera.log"),
                   "RUNSTART": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "SITE": "Empty",
                   "IPRANGE": "10.0.0.1-10.0.0.9", "ADDRCOUNT": "9", "ANSWERED": "0", "CANDS": "0",
                   "RUNCOUNT": "0", "LOCALAPPDATA": tmp}
            result = run_block("RPT", env)
            self.assertEqual(result.stdout.strip(), "0|0|0|0|0", result.stderr)
            self.assertFalse((stage / "settings.csv").exists())
            self.assertFalse((stage / "subnets").exists())
            self.assertIn("Exported to CSV    : 0", (stage / "camera.log").read_text())


if __name__ == "__main__":
    unittest.main()
