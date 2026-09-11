"""The whole script, start to zip, with a stand-in for CCT-Batch: the sweep finds three cameras in
two of three subnets, the stand-in exports them and fails one subnet, and the zip, the logs, the
exit code and the screen must all say so."""
import datetime
import tempfile
import unittest
import zipfile
from pathlib import Path

from .support import (CCT_LOG_DIR, Listener, prepare_script, prepare_stub, run_script, today_log_name,
                      utf16_lines)

ANSWERS = ["Test Site", "127.0.0.1", "127.0.2.255", "admin", "pw", "18099", "18098"]
PLAN = {"cameras": {"127.0.0.10": "Cam A", "127.0.0.11": "Cam B", "127.0.2.7": "Cam C", "127.0.2.8": "!Cam D"},
        "exit": {"127.0.2.0-127.0.2.255": 6}}


class ExportWithStubTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        work = Path(cls.tmp.name)
        cls.appdata = work / "appdata"
        log_dir = cls.appdata / CCT_LOG_DIR
        log_dir.mkdir(parents=True)
        (log_dir / today_log_name()).write_text("10.20.1.99      LoggedIn            Old camera\n",
                                                encoding="utf-8")
        (work / "temp").mkdir()

        stub = prepare_stub(work, PLAN)
        cls.script = prepare_script(work, stub)
        env = {"TEMP": str(work / "temp"), "TMP": str(work / "temp"), "LOCALAPPDATA": str(cls.appdata),
               "CCT_STUB_PLAN": str(stub.parent / "plan.json")}
        with Listener("127.0.0.10", 18099), Listener("127.0.0.11", 18099), \
                Listener("127.0.2.7", 18098), Listener("127.0.2.8", 18098):
            cls.result = run_script(cls.script, ANSWERS, env, timeout=300)
        zips = list(work.glob("*.zip"))
        assert len(zips) == 1, (zips, cls.result.stdout, cls.result.stderr)
        cls.zip = zips[0]
        cls.unpacked = work / "unpacked"
        with zipfile.ZipFile(cls.zip) as z:
            z.extractall(cls.unpacked)
            cls.entries = sorted(n.replace("\\", "/") for n in z.namelist())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_exit_code_and_zip_name(self):
        self.assertEqual(self.result.returncode, 11, self.result.stdout + self.result.stderr)
        stamp = datetime.date.today().strftime("%d_%m_%y")
        self.assertEqual(self.zip.name, f"Test Site_ACC_Camera_Settings_{stamp}.zip")

    def backup(self) -> str:
        """CCT's own file, named 'backup': no date, and no extension on purpose - a double-click asks
        what to open it with rather than launching Excel."""
        return next(n for n in self.entries if n == "backup")

    def test_zip_holds_the_documented_files_and_nothing_else(self):
        backup = self.backup()
        self.assertEqual([n for n in self.entries if n != backup],
                         ["analytics.csv", "camera.log", "console.log", "import.log", "settings.csv",
                          "subnets/127.0.0.1.csv", "subnets/127.0.2.0.csv"])

    def test_staging_folder_is_gone(self):
        self.assertEqual(list((Path(self.tmp.name) / "temp").glob("*_ACC_Camera_Settings_*")), [])

    def test_the_backup_file_merges_both_subnets_as_cct_wrote_them(self):
        lines = utf16_lines(self.unpacked / self.backup())
        self.assertEqual(sum(1 for ln in lines if ln.startswith("DeviceHeader")), 1)
        self.assertEqual(sum(1 for ln in lines if ln.startswith("AnalyticsHeader")), 1)
        self.assertEqual([ln.split("\t")[11] for ln in lines if ln.startswith("Device\t")],
                         ["127.0.0.10", "127.0.0.11", "127.0.2.7"])

    def test_settings_csv_is_the_readable_copy(self):
        raw = (self.unpacked / "settings.csv").read_bytes()
        self.assertEqual(raw[:3], b"\xef\xbb\xbf")
        lines = raw.decode("utf-8-sig").splitlines()
        self.assertTrue(lines[0].startswith("MacAddress,Name,Location,SerialNumber,"), lines[0])
        self.assertEqual([ln.split(",")[2 - 1] for ln in lines[1:]], ["Cam A", "Cam B", "Cam C"])
        heads = (self.unpacked / "analytics.csv").read_bytes().decode("utf-8-sig").splitlines()
        self.assertEqual(heads[0], "MacAddress,Name,IpAddress,Head,AnalyticsEnabled")
        self.assertEqual(len(heads), 4)

    def test_import_log_carries_the_site_verdict(self):
        log = (self.unpacked / "import.log").read_text(encoding="cp1252")
        self.assertIn("Sweep       : 767 answered ping, 4 with a web port open, in 2 subnets", log)
        self.assertIn("Subnets     : 1 exported, 0 had no camera, 1 need a re-run", log)
        self.assertIn("Script exit : 11", log)
        self.assertIn("Result      : PARTIAL - 1 of 2 subnets need a re-run. camera.log names them", log)
        self.assertIn("Exported    : 3 cameras", log)
        self.assertIn(f"Readable    : settings.csv holds 3 cameras, analytics.csv 3 heads; {self.backup()} is CCT's own file", log)
        self.assertIn("Attention   : 1 cameras answered but did not log in", log)
        self.assertNotIn("pw", log.split("Username")[1].split("\n")[0])

    def test_camera_log_names_the_subnet_to_re_run_and_the_bad_camera(self):
        report = (self.unpacked / "camera.log").read_text(encoding="cp1252")
        self.assertIn("RE-RUN THESE SUBNETS on their own", report)
        self.assertIn("  127.0.2.0-127.0.2.255\n", report)
        self.assertIn("127.0.0.1-127.0.0.255             255     2        2   SUCCESS", report)
        self.assertIn("127.0.1.0-127.0.1.255             256     0        -   skipped - no web port open",
                      report)
        self.assertIn("127.0.2.0-127.0.2.255             256     2        1   "
                      "PARTIAL - at least one camera failed", report)
        self.assertIn("127.0.2.8       InvalidCredentials", report)
        self.assertNotIn("Old camera", report)

    def test_console_log_is_this_run_only(self):
        console = (self.unpacked / "console.log").read_text(encoding="cp1252")
        self.assertNotIn("Old camera", console)
        self.assertIn("Cam C", console)

    def test_screen_walks_the_technician_through_it(self):
        out = self.result.stdout
        self.assertIn("Subnet 1 of 2  -  127.0.0.1-127.0.0.255", out)
        self.assertIn("Subnet 2 of 2  -  127.0.2.0-127.0.2.255", out)
        self.assertIn("PARTIAL - 1 of 2 subnets need a re-run", out)
        self.assertIn("Cameras exported : 3", out)
        self.assertIn("NEEDS ATTENTION  : 1 cameras", out)
        self.assertIn("camera.log names each subnet that needs a re-run", out)


if __name__ == "__main__":
    unittest.main()
