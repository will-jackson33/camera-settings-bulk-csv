"""The whole script against the real CCT-Batch, on loopback. Every 127.x address answers ping; one
listener makes one address look like it has a web port; CCT gets exactly that subnet, finds no
camera behind it, and the script must say so honestly. About two minutes, all of it CCT's."""
import tempfile
import unittest
import zipfile
from pathlib import Path

from .support import CCT_EXE, Listener, prepare_script, run_script

ANSWERS = ["Loopback", "127.0.0.1", "127.0.2.255", "admin", "admin", "18099", "18098"]


@unittest.skipUnless(CCT_EXE.exists(), "CCT-Batch is not installed on this machine")
class ExportWithRealCctTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        work = Path(cls.tmp.name)
        (work / "temp").mkdir()
        cls.script = prepare_script(work, None)
        env = {"TEMP": str(work / "temp"), "TMP": str(work / "temp")}
        with Listener("127.0.1.5", 18099):
            cls.result = run_script(cls.script, ANSWERS, env, timeout=600)
        zips = list(work.glob("*.zip"))
        assert len(zips) == 1, (zips, cls.result.stdout, cls.result.stderr)
        cls.unpacked = work / "unpacked"
        with zipfile.ZipFile(zips[0]) as z:
            z.extractall(cls.unpacked)
            cls.entries = sorted(n.replace("\\", "/") for n in z.namelist())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_one_subnet_reached_cct_and_it_found_nothing(self):
        self.assertEqual(self.result.returncode, 2, self.result.stdout + self.result.stderr)
        self.assertEqual(self.entries, ["camera.log", "console.log", "import.log"])
        log = (self.unpacked / "import.log").read_text(encoding="cp1252")
        self.assertIn("Sweep       : 767 answered ping, 1 with a web port open, in 1 subnets", log)
        self.assertIn("Subnets     : 0 exported, 1 had no camera, 0 need a re-run", log)
        self.assertIn("Result      : FAILED - addresses answered, but no camera logged in", log)

    def test_camera_log_shows_cct_ran_that_subnet_within_budget(self):
        report = (self.unpacked / "camera.log").read_text(encoding="cp1252")
        line = next(ln for ln in report.splitlines() if ln.strip().startswith("127.0.1.0-127.0.1.255"))
        self.assertIn("no camera logged in  (", line)
        seconds = int(line.split("(")[1].split(" s)")[0])
        self.assertLess(seconds, 115, line)
        self.assertGreater(seconds, 60, line)
        self.assertIn("  127.0.1.5\n", report.split("but CCT reported no camera there")[1])

    def test_console_log_is_ccts_own_output(self):
        console = (self.unpacked / "console.log").read_text(encoding="cp1252")
        self.assertIn("batch job version", console)
        self.assertIn("Device not found or you use incorrect credentials", console)
        self.assertIn("Subnet 1 of 1  -  127.0.1.0-127.0.1.255", self.result.stdout)


if __name__ == "__main__":
    unittest.main()
