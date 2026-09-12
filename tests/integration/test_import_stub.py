"""The import script, start to zip, against the stand-in CCT: the gates in order, a camera whose
change does not take, a camera that did not answer, a confirmation typed wrongly, a file that sets
a password, a file with nothing left to do, the readable file a person edited in Excel, the
rollback handed in as a file, and the runs that never touch a camera that is not changing."""

from __future__ import annotations

import csv
import datetime
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from .stub_cct import HEADER, device_rows
from .support import CCT_LOG_DIR, IMPORT_BAT, prepare_script, prepare_stub, run_script, utf16_lines

CAMERAS = {"127.0.0.10": "Cam A", "127.0.0.11": "Cam B", "127.0.2.7": "Cam C"}


def ordered(names: dict[str, str]) -> list[str]:
    return sorted(names, key=lambda ip: tuple(int(o) for o in ip.split(".")))


def write_import_file(path: Path, names: dict[str, str], password: str = "", dhcp: bool = False) -> None:
    """A settings file to import, in the stand-in's own row shape, carrying the names asked for."""
    rows = list(HEADER)
    for n, ip in enumerate(ordered(names), 1):
        device, analytics = device_rows(n, ip, names[ip])
        if dhcp:
            device = device.replace("\tFalse\tTrue\t80;443\t", "\tTrue\tTrue\t80;443\t", 1)
        rows += [device + password, analytics]  # the row ends with the two empty credential fields
    path.write_text("\n".join(rows) + "\n", encoding="utf-16", newline="\r\n")


def write_readable_pair(path: Path, names: dict[str, str], cells: dict[str, str] | None = None,
                        dhcp: bool = False) -> None:
    """The same cameras as the export's readable settings.csv and analytics.csv beside it, with
    any cell overridden as a person might have typed it in Excel."""
    columns = HEADER[0].split("\t")[1:]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(columns)
        for n, ip in enumerate(ordered(names), 1):
            values = [v.strip("\"'") for v in device_rows(n, ip, names[ip])[0].split("\t")[1:]]
            row = dict(zip(columns, values, strict=True))
            if dhcp:
                row["DHCPEnabled"] = "True"
            row.update(cells or {})
            writer.writerow([row[c] for c in columns])
    with path.with_name("analytics.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(["MacAddress", "Name", "IpAddress", "Head", "AnalyticsEnabled"])
        for n, ip in enumerate(ordered(names), 1):
            mac = device_rows(n, ip, names[ip])[0].split("\t")[1]
            writer.writerow([mac, names[ip], ip, "1", "True"])


class ImportRun:
    """One run of the import script against a fresh stand-in, with everything it left behind.

    readable: the file is the readable pair rather than CCT's own, with these cells overridden.
    rollback: "cct" or "readable" hands the site's current state in as the rollback file instead
    of leaving the field blank, which exports one.
    """

    def __init__(self, names: dict[str, str], typed: list[str], plan_extra: dict | None = None, password: str = "",
                 readable: dict[str, str] | None = None, rollback: str | None = None, drop: bool = False,
                 dhcp: bool = False, move: tuple[str, str] | None = None):
        self.tmp = tempfile.TemporaryDirectory()
        work = Path(self.tmp.name)
        (work / "appdata" / CCT_LOG_DIR).mkdir(parents=True)
        (work / "temp").mkdir()
        (work / "drop").mkdir()
        plan = {"cameras": CAMERAS, **(plan_extra or {})}
        self.stub = prepare_stub(work, plan)
        self.script = prepare_script(work, self.stub, script=IMPORT_BAT, cct_calls=2)
        if readable is None:
            self.csv = work / "drop" / "settings.edited.csv"
            write_import_file(self.csv, names, password, dhcp=dhcp)
        else:
            self.csv = work / "drop" / "settings.csv"
            write_readable_pair(self.csv, names, readable, dhcp=dhcp)
            if move is not None:
                # One camera given a new address, the way a person edits a single row in Excel.
                rows = list(csv.reader(self.csv.read_text(encoding="utf-8-sig").splitlines()))
                at = rows[0].index("IpAddress")
                for row in rows[1:]:
                    if row[at] == move[0]:
                        row[at] = move[1]
                with self.csv.open("w", encoding="utf-8-sig", newline="") as handle:
                    csv.writer(handle, lineterminator="\r\n").writerows(rows)
        self.rollback = ""
        if rollback is not None:
            current = {ip: name.lstrip("!") for ip, name in plan["cameras"].items()}
            (work / "drop" / "rollback").mkdir()
            if rollback == "cct":
                self.rollback = str(work / "drop" / "rollback" / "cct.csv")
                write_import_file(Path(self.rollback), current, dhcp=dhcp)
            elif rollback == "beside":
                # The export's own backup file beside the dropped file: the form offers it, and the
                # blank answer keeps what is offered.
                self.beside = work / "drop" / "backup"
                write_import_file(self.beside, current)
            else:
                self.rollback = str(work / "drop" / "rollback" / "settings.csv")
                write_readable_pair(Path(self.rollback), current)
        env = {"TEMP": str(work / "temp"), "TMP": str(work / "temp"), "LOCALAPPDATA": str(work / "appdata"),
               "CCT_STUB_PLAN": str(self.stub.parent / "plan.json")}
        # drop=True hands the file over the way Explorer does - as an argument - and leaves the
        # form's file field blank, so the run only succeeds if the dropped path reached the form.
        typed_path = "" if drop else str(self.csv)
        answers = ["Test Site", typed_path, self.rollback, "admin", "pw", "18099", "18098"] + typed
        self.result = run_script(self.script, answers, env, timeout=300,
                                 args=[str(self.csv)] if drop else None)
        zips = list(work.glob("*.zip"))
        assert len(zips) == 1, (zips, self.result.stdout, self.result.stderr)
        self.zip = zips[0]
        self.unpacked = work / "unpacked"
        with zipfile.ZipFile(self.zip) as z:
            z.extractall(self.unpacked)
            self.entries = sorted(n.replace("\\", "/") for n in z.namelist())
        imports = self.stub.parent / "imports.log"
        self.imports = imports.read_text(encoding="utf-8").splitlines() if imports.exists() else []
        # A run that stops before CCT is ever called leaves the stand-in untouched, and the site as
        # the plan described it.
        state = self.stub.parent / "state.json"
        self.state = (json.loads(state.read_text(encoding="utf-8")) if state.exists()
                      else {"cameras": {ip: {"name": name.lstrip("!")} for ip, name in plan["cameras"].items()}})

    def text(self, name: str) -> str:
        return (self.unpacked / name).read_text(encoding="cp1252")

    def device_row(self, name: str, mac: str) -> list[str]:
        """One camera's row out of a settings file in the zip, field by field."""
        rows = [ln.split("\t") for ln in utf16_lines(self.unpacked / name) if ln.startswith("Device\t")]
        return next(r for r in rows if r[1] == mac)

    def device_names(self, name: str) -> list[str]:
        return [ln.split("\t")[2] for ln in utf16_lines(self.unpacked / name) if ln.startswith("Device\t")]

    def close(self) -> None:
        self.tmp.cleanup()


class ImportAppliesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Two renames asked for; the stand-in refuses to apply the one on 127.0.0.11, which is how
        # a camera that accepts the write and keeps its old value looks from outside.
        cls.session = ImportRun({"127.0.0.10": "Cam A renamed", "127.0.0.11": "Cam B renamed", "127.0.2.7": "Cam C"},
                                ["n", "Test Site"], plan_extra={"ignore_import": ["127.0.0.11"]})

    @classmethod
    def tearDownClass(cls):
        cls.session.close()

    def test_exit_code_zip_name_and_contents(self):
        self.assertEqual(self.session.result.returncode, 11, self.session.result.stdout + self.session.result.stderr)
        stamp = datetime.date.today().strftime("%d_%m_%y")
        self.assertEqual(self.session.zip.name, f"Test Site_ACC_Camera_Import_{stamp}.zip")
        self.assertEqual(self.session.entries, ["after.csv", "camera.log", "changes.csv", "console.log", "edited.csv",
                                                "import.log", "rollback", "settings.csv"])
        self.assertEqual((self.session.unpacked / "edited.csv").read_bytes(), self.session.csv.read_bytes())

    def test_cct_was_given_only_the_cameras_that_change(self):
        self.assertEqual(self.session.device_names("settings.csv"), ['"Cam A renamed"', '"Cam B renamed"'])

    def test_the_runs_in_order_and_only_over_the_changed_cameras(self):
        self.assertEqual(self.session.imports, ["127.0.0.10-127.0.0.11 settings.csv edited=1"])
        out = self.session.result.stdout
        self.assertIn("rollback export  -  run 1 of 2  -  127.0.0.10-127.0.0.11", out)
        self.assertIn("rollback export  -  run 2 of 2  -  127.0.2.7", out)
        self.assertLess(out.index("rollback export  -  run 2 of 2"), out.index("IMPORT  -  run 1 of 1  -  127.0.0.10-127.0.0.11"))
        self.assertLess(out.index("IMPORT  -  run 1 of 1"), out.index("after export  -  run 1 of 1  -  127.0.0.10-127.0.0.11"))

    def test_rollback_is_the_state_before_and_after_is_the_changed_cameras_now(self):
        self.assertEqual(self.session.device_names("rollback"), ['"Cam A"', '"Cam B"', '"Cam C"'])
        self.assertEqual(self.session.device_names("after.csv"), ['"Cam A renamed"', '"Cam B"'])
        self.assertEqual(self.session.state["cameras"]["127.0.0.10"]["name"], "Cam A renamed")
        self.assertEqual(self.session.state["cameras"]["127.0.0.11"]["name"], "Cam B")
        self.assertEqual(self.session.state["cameras"]["127.0.2.7"]["name"], "Cam C")

    def test_logs_say_what_was_intended_and_what_did_not_take(self):
        log = self.session.text("import.log")
        self.assertIn("Rollback    : exported now, one CCT run per group", log)
        self.assertIn("Compared    : 0 cameras in the file not in the rollback; 2 settings on 2 cameras to change", log)
        self.assertIn("Written to  : 2 cameras in 1 CCT runs, 1 runs to prove it - no other camera logged into", log)
        self.assertIn("After       : 1 settings did not take, 0 cameras not reached, 0 CCT runs failed", log)
        self.assertIn("Result      : PARTIAL - 1 settings did not take and 0 CCT runs failed", log)
        self.assertNotIn("pw", log.split("Username")[1].split("\n")[0])
        report = self.session.text("camera.log")
        self.assertIn("Intended changes   : 2 settings on 2 cameras", report)
        self.assertIn("Written to         : 2 cameras in 1 CCT runs - no other camera was logged into", report)
        self.assertIn("DID NOT TAKE - still different after the import:", report)
        self.assertIn("Name", report.split("DID NOT TAKE")[1].split("\n")[1])
        self.assertIn("  Cam B (127.0.0.11)   Name\n      from  'Cam B'\n      to    'Cam B renamed'", report)
        self.assertIn("INTENDED - what the file changed against the rollback:", report)
        # The stand-in answers in a second or two; only the shape of the tables is asserted.
        self.assertRegex(report, r"Rollback export, one run per group of cameras in the file:\n  127\.0\.0\.10-127\.0\.0\.11 +exit 0 in \d+ s\n"
                                 r"  127\.0\.2\.7 +exit 0 in \d+ s\n")
        self.assertRegex(report, r"Import, one run per group of neighbouring changed cameras:\n  127\.0\.0\.10-127\.0\.0\.11 +exit 0 in \d+ s\n")
        self.assertRegex(report, r"Proof export, the same cameras read back:\n  127\.0\.0\.10-127\.0\.0\.11 +exit 0 in \d+ s\n")

    def test_screen_shows_the_plan_before_asking(self):
        out = self.session.result.stdout
        self.assertIn("Importing from a file of 3 cameras in 2 subnets", out)
        self.assertIn("Format           : the file as CCT wrote it", out)
        self.assertIn("Rollback         : exported now", out)
        self.assertIn("Rollback             : exported just now", out)
        self.assertIn("Answered just now    : 3 of the 3 cameras in the file", out)
        self.assertIn("Settings to change   : 2   (Name 2)", out)
        self.assertIn("Cameras to change    : 2   (every other camera is left alone", out)
        self.assertIn("CCT runs             : 1 to import, 1 to prove it - roughly 30 s in all\n    127.0.0.10-127.0.0.11\n", out)
        self.assertIn("Type the site name exactly as above", out)
        self.assertIn("PARTIAL - 1 settings did not take", out)
        self.assertLess(out.index("Settings to change"), out.index("Type the site name"))


class OnlyTheChangedCamerasTest(unittest.TestCase):
    """CCT is handed only the cameras that change, in ranges that never hold one that does not."""

    SITE = {"127.0.0.10": "Cam A", "127.0.0.11": "Cam B", "127.0.0.12": "Cam C", "127.0.0.13": "Cam D", "127.0.2.7": "Cam E"}

    def test_neighbours_share_a_run_and_an_unchanged_camera_between_them_splits_it(self):
        names = dict(self.SITE)
        names.update({"127.0.0.10": "A2", "127.0.0.12": "C2", "127.0.0.13": "D2"})
        run = ImportRun(names, ["n", "Test Site"], plan_extra={"cameras": self.SITE})
        try:
            self.assertEqual(run.result.returncode, 0, run.result.stdout + run.result.stderr)
            self.assertEqual(run.imports, ["127.0.0.10 settings.csv edited=1", "127.0.0.12-127.0.0.13 settings.csv edited=2"])
            self.assertEqual(run.device_names("settings.csv"), ['"A2"', '"C2"', '"D2"'])
            self.assertEqual([run.state["cameras"][ip]["name"] for ip in ordered(self.SITE)], ["A2", "Cam B", "C2", "D2", "Cam E"])
            self.assertIn("CCT runs             : 2 to import, 2 to prove it - roughly 60 s in all\n"
                          "    127.0.0.10\n    127.0.0.12-127.0.0.13\n", run.result.stdout)
            self.assertIn("IMPORT  -  run 2 of 2  -  127.0.0.12-127.0.0.13", run.result.stdout)
        finally:
            run.close()


class RollbackGivenTest(unittest.TestCase):
    """The rollback handed in as a file: no export first, and the same narrow import."""

    def test_cct_own_file_as_the_rollback(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["n", "Test Site"], rollback="cct")
        try:
            self.assertEqual(run.result.returncode, 0, run.result.stdout + run.result.stderr)
            self.assertNotIn("rollback export", run.result.stdout)
            self.assertIn("Rollback         : " + run.rollback, run.result.stdout)
            self.assertIn("Rollback             : from the file, 3 cameras\n", run.result.stdout)
            self.assertIn("In the rollback      : 1 of the 1 cameras in the file (not checked online", run.result.stdout)
            self.assertEqual(run.imports, ["127.0.0.10 settings.csv edited=1"])
            self.assertEqual(run.device_names("rollback"), ['"Cam A"', '"Cam B"', '"Cam C"'])
            self.assertEqual(run.state["cameras"]["127.0.0.10"]["name"], "Cam A renamed")
            self.assertIn("Rollback    : from the file " + run.rollback, run.text("import.log"))
            self.assertNotIn("Rollback export, one run per subnet", run.text("camera.log"))
            self.assertIn("SUCCESS - every change in the file is now on the cameras: 1 settings on 1 cameras", run.text("import.log"))
        finally:
            run.close()

    def test_the_backup_file_beside_the_dropped_file_is_offered_and_enter_keeps_it(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["n", "Test Site"], readable={}, rollback="beside")
        try:
            self.assertEqual(run.result.returncode, 0, run.result.stdout + run.result.stderr)
            self.assertNotIn("rollback export", run.result.stdout)
            # The form reports the long path; the harness's temp folder is spelt in 8.3 form.
            self.assertRegex(run.result.stdout, r"Rollback         : .*\\drop\\backup\n")
            self.assertEqual(run.imports, ["127.0.0.10 settings.csv edited=1"])
            self.assertEqual(run.device_names("rollback"), ['"Cam A"', '"Cam B"', '"Cam C"'])
        finally:
            run.close()

    def test_a_dropped_file_reaches_the_form(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["n", "Test Site"], readable={}, rollback="cct", drop=True)
        try:
            self.assertEqual(run.result.returncode, 0, run.result.stdout + run.result.stderr)
            # Plain mode never echoes a field's default, so the proof is that the run went
            # through on a blank answer: only the dropped path could have filled that field.
            self.assertEqual(run.imports, ["127.0.0.10 settings.csv edited=1"])
        finally:
            run.close()

    def test_the_readable_pair_as_the_rollback(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["n", "Test Site"], rollback="readable")
        try:
            self.assertEqual(run.result.returncode, 0, run.result.stdout + run.result.stderr)
            self.assertEqual(run.imports, ["127.0.0.10 settings.csv edited=1"])
            self.assertEqual(run.device_names("rollback"), ['"Cam A"', '"Cam B"', '"Cam C"'])
            self.assertEqual(run.state["cameras"]["127.0.0.10"]["name"], "Cam A renamed")
        finally:
            run.close()

    def test_a_camera_not_in_the_rollback_file_stops_before_anything(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed", "127.0.1.99": "Ghost"}, ["n", "Test Site"], rollback="cct")
        try:
            self.assertEqual(run.result.returncode, 3, run.result.stdout + run.result.stderr)
            self.assertEqual(run.imports, [])
            self.assertIn("NOT IN THE ROLLBACK FILE - the import stops here, nothing is changed:", run.result.stdout)
            self.assertIn("    Ghost (127.0.1.99)", run.result.stdout)
            self.assertIn("Result      : STOPPED - 1 cameras in the file are not in the rollback file", run.text("import.log"))
            self.assertEqual(run.state["cameras"]["127.0.0.10"]["name"], "Cam A")
        finally:
            run.close()


class NetworkChangeTest(unittest.TestCase):
    """The four network columns, which CCT validates together and which can lose a camera."""

    SITE = {"127.0.0.10": "Cam A", "127.0.0.11": "Cam B", "127.0.0.12": "Cam C"}
    MAC_A = "00-18-85-00-00-0A"
    MAC_C = "00-18-85-00-00-0C"

    def test_a_changed_address_is_sent_as_a_static_one(self):
        # The live case: a DHCP camera given a new address. Sending the new address with DHCP
        # still on is what CCT refuses as IpAddressAndDHCP, and it refuses the whole file for it.
        run = ImportRun(dict(self.SITE), ["n", ""], plan_extra={"cameras": self.SITE}, dhcp=True,
                        readable={}, rollback="cct", move=("127.0.0.10", "127.0.0.40"))
        try:
            row = run.device_row("settings.csv", self.MAC_A)
            self.assertEqual(row[8], "False", "DHCP must be switched off for a static address")
            self.assertEqual(row[11], "127.0.0.40")
            self.assertEqual(row[12], "255.255.255.0", "the mask has to ride along or CCT refuses it")
            self.assertEqual(row[13], "127.0.0.1", "and the gateway")
            self.assertIn("NETWORK CHANGES - written last, after every other camera:", run.result.stdout)
            self.assertIn("127.0.0.10  ->  127.0.0.40   set static", run.result.stdout)
            self.assertIn("cannot be reached by the", run.result.stdout)
        finally:
            run.close()

    def test_an_address_that_is_not_changing_is_not_sent_at_all(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["n", ""], plan_extra={"cameras": self.SITE},
                        dhcp=True, readable={}, rollback="cct")
        try:
            row = run.device_row("settings.csv", self.MAC_A)
            self.assertEqual(row[8], "True", "the camera stays on DHCP")
            self.assertEqual([row[11], row[12], row[13]], ["", "", ""],
                             "blank is the only value a drifted rollback cannot get the file refused for")
            self.assertNotIn("NETWORK CHANGES", run.result.stdout)
        finally:
            run.close()

    def test_a_static_camera_keeps_its_address_because_cct_requires_it(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["n", ""], plan_extra={"cameras": self.SITE},
                        readable={}, rollback="cct")
        try:
            row = run.device_row("settings.csv", self.MAC_A)
            self.assertEqual(row[8], "False")
            self.assertEqual([row[11], row[12], row[13]], ["127.0.0.10", "255.255.255.0", "127.0.0.1"])
        finally:
            run.close()

    def test_switching_a_static_camera_to_dhcp(self):
        # The other direction: the person sets DHCPEnabled True on a camera that has a fixed
        # address. The address columns go blank - CCT needs them blank or unchanged with DHCP on -
        # and the camera is written last like any other network change.
        run = ImportRun({"127.0.0.10": "Cam A"}, ["n", ""], plan_extra={"cameras": self.SITE},
                        readable={"DHCPEnabled": "True"}, rollback="cct")
        try:
            row = run.device_row("settings.csv", self.MAC_A)
            self.assertEqual(row[8], "True")
            self.assertEqual([row[11], row[12], row[13]], ["", "", ""])
            self.assertIn("NETWORK CHANGES - written last, after every other camera:", run.result.stdout)
            self.assertIn("handed to DHCP", run.result.stdout)
            self.assertIn("an address DHCP gives it", run.result.stdout)
        finally:
            run.close()

    def test_the_camera_that_moves_is_written_last(self):
        # Cam C is renamed and Cam A is moving: the rename goes first, on its own run, and the
        # address change follows. A run never spans the other group.
        names = dict(self.SITE)
        names["127.0.0.12"] = "Cam C renamed"
        run = ImportRun(names, ["n", "Test Site"], plan_extra={"cameras": self.SITE}, dhcp=True,
                        readable={}, rollback="cct", move=("127.0.0.10", "127.0.0.40"))
        try:
            out = run.result.stdout
            self.assertIn("IMPORT  -  run 1 of 2  -  127.0.0.12", out)
            self.assertIn("IMPORT  -  run 2 of 2  -  127.0.0.10", out)
            self.assertLess(out.index("run 1 of 2  -  127.0.0.12"), out.index("run 2 of 2  -  127.0.0.10"))
        finally:
            run.close()


class ReadableFileTest(unittest.TestCase):
    """The file a person edited in Excel imports exactly as CCT's own would."""

    def test_a_rename_in_the_readable_file_reaches_the_camera(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["n", "Test Site"], readable={})
        try:
            self.assertEqual(run.result.returncode, 0, run.result.stdout + run.result.stderr)
            self.assertIn("Format           : readable settings.csv, one row per camera", run.result.stdout)
            self.assertEqual(run.imports, ["127.0.0.10 settings.csv edited=1"])
            self.assertEqual(run.state["cameras"]["127.0.0.10"]["name"], "Cam A renamed")
            self.assertIn("SUCCESS - every change in the file is now on the cameras: 1 settings on 1 cameras",
                          run.text("import.log"))
            self.assertIn("edited-analytics.csv", run.entries)
            settings = utf16_lines(run.unpacked / "settings.csv")
            self.assertTrue(settings[0].startswith("DeviceHeader\tMacAddress\tName\t"), settings[0])
            self.assertIn('Device\t00-18-85-00-00-0A\t"Cam A renamed"\t"Site"\t\'SN0001\'\t"4.2.0.10"\tH4A-B', settings[2])
        finally:
            run.close()

    def test_excels_own_rewrites_are_not_changes(self):
        run = ImportRun({"127.0.0.10": "Cam A"}, [], readable={"DHCPEnabled": "FALSE", "UseHttps": "true"})
        try:
            self.assertEqual(run.result.returncode, 2, run.result.stdout + run.result.stderr)
            self.assertEqual(run.imports, [])
            self.assertIn("NOTHING TO DO - the cameras already hold every setting in the file", run.text("import.log"))
        finally:
            run.close()

    def test_a_cell_the_column_cannot_read_is_left_as_it_is_and_the_rest_goes_ahead(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["n", "Test Site"], readable={"DHCPEnabled": "maybe"})
        try:
            self.assertEqual(run.result.returncode, 0, run.result.stdout + run.result.stderr)
            self.assertIn("LEFT AS THEY ARE - 1 cells could not be read, so nothing is written for them and the\n"
                          "  camera keeps what it has.", run.result.stdout)
            self.assertIn("Cam A (127.0.0.10)   DHCPEnabled   'maybe'", run.result.stdout)
            self.assertIn("DHCPEnabled takes True or False, not 'maybe'", run.result.stdout)
            self.assertIn("Settings to change   : 1   (Name 1)", run.result.stdout)
            self.assertEqual(run.imports, ["127.0.0.10 settings.csv edited=1"])
            self.assertEqual(run.state["cameras"]["127.0.0.10"]["name"], "Cam A renamed")
            # The row CCT was given is the rollback's own with the name applied: DHCPEnabled untouched.
            given = [ln for ln in utf16_lines(run.unpacked / "settings.csv") if ln.startswith("Device\t")]
            self.assertEqual(given[0].split("\t")[8], "False")
            self.assertIn("SUCCESS - every readable change is on the cameras: 1 settings on 1 cameras", run.text("import.log"))
            self.assertIn("Left as they were: 1 cells the columns could not read - nothing was written for them. camera.log names each",
                          run.result.stdout)
            self.assertIn("Compared    : 0 cameras in the file not in the rollback; 1 settings on 1 cameras to change; 1 cells left as they were",
                          run.text("import.log"))
            report = run.text("camera.log")
            self.assertIn("Left as they were  : 1 cells the file held a value the column cannot read", report)
            self.assertIn("LEFT AS THEY WERE - cells the column could not read; nothing was written for them:\n"
                          "  Cam A (127.0.0.10)   DHCPEnabled   'maybe'\n      DHCPEnabled takes True or False, not 'maybe'\n", report)
        finally:
            run.close()

    def test_only_unreadable_cells_is_nothing_to_do(self):
        run = ImportRun({"127.0.0.10": "Cam A"}, [], readable={"DHCPEnabled": "maybe"})
        try:
            self.assertEqual(run.result.returncode, 2, run.result.stdout + run.result.stderr)
            self.assertEqual(run.imports, [])
            self.assertNotIn("Type the site name", run.result.stdout)
            self.assertIn("NOTHING TO DO - only unreadable cells differ, left as they are. Nothing was changed", run.text("import.log"))
        finally:
            run.close()


class CameraDidNotAnswerTest(unittest.TestCase):
    def test_stops_before_any_import(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed", "127.0.1.99": "Ghost"}, ["n", "Test Site"])
        try:
            self.assertEqual(run.result.returncode, 3, run.result.stdout + run.result.stderr)
            self.assertEqual(run.imports, [])
            self.assertIn("DID NOT ANSWER - the import stops here, nothing is changed:", run.result.stdout)
            self.assertIn("    Ghost (127.0.1.99)", run.result.stdout)
            self.assertIn("Result      : STOPPED - 1 cameras in the file did not answer", run.text("import.log"))
            self.assertIn("rollback", run.entries)
            self.assertNotIn("after.csv", run.entries)
            self.assertEqual(run.state["cameras"]["127.0.0.10"]["name"], "Cam A")
        finally:
            run.close()


class ConfirmationTest(unittest.TestCase):
    def test_the_site_name_typed_wrongly_three_times_stops(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["n", "Wrong", "Wrong", "Wrong"])
        try:
            self.assertEqual(run.result.returncode, 3, run.result.stdout)
            self.assertEqual(run.imports, [])
            self.assertIn("That is not the site name.", run.result.stdout)
            self.assertIn("STOPPED - the confirmation was not typed", run.text("import.log"))
            self.assertEqual(run.state["cameras"]["127.0.0.10"]["name"], "Cam A")
        finally:
            run.close()

    def test_enter_at_the_confirmation_stops(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["n", ""])
        try:
            self.assertEqual(run.result.returncode, 3, run.result.stdout)
            self.assertEqual(run.imports, [])
            self.assertIn("STOPPED at the confirmation", run.text("import.log"))
        finally:
            run.close()

    def test_a_password_needs_rotate_as_well(self):
        run = ImportRun({"127.0.0.10": "Cam A"}, ["n", "Test Site", "ROTATE"], password="Test!!2026")
        try:
            self.assertEqual(run.result.returncode, 0, run.result.stdout + run.result.stderr)
            self.assertIn("PASSWORDS        : this file sets 1 camera passwords.", run.result.stdout)
            self.assertIn("Type ROTATE to change passwords", run.result.stdout)
            self.assertIn("Passwords   : 1 set by the file", run.text("import.log"))
            self.assertIn("SUCCESS - every change in the file is now on the cameras", run.text("import.log"))
            self.assertNotIn("Test!!2026", run.text("camera.log"))
            self.assertNotIn("Test!!2026", run.text("import.log"))
            self.assertNotIn("Test!!2026", run.text("changes.csv"))
            self.assertEqual(len(run.imports), 1)
            given = [ln for ln in utf16_lines(run.unpacked / "settings.csv") if ln.startswith("Device\t")]
            self.assertEqual(len(given), 1)
            self.assertTrue(given[0].endswith("\tTest!!2026"), given[0])
        finally:
            run.close()

    def test_a_wrong_word_at_the_password_gate_stops(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["n", "Test Site", "yes", "y", "ROTATE!"], password="Test!!2026")
        try:
            self.assertEqual(run.result.returncode, 3, run.result.stdout)
            self.assertEqual(run.imports, [])
            self.assertIn("STOPPED - the confirmation was not typed", run.text("import.log"))
            self.assertEqual(run.state["cameras"]["127.0.0.10"]["name"], "Cam A")
        finally:
            run.close()

    def test_y_at_the_change_list_writes_it_beside_the_script(self):
        run = ImportRun({"127.0.0.10": "Cam A renamed"}, ["y", "Test Site"])
        try:
            self.assertEqual(run.result.returncode, 0, run.result.stdout + run.result.stderr)
            changes = run.zip.with_name(run.zip.stem + "-changes.csv")
            self.assertIn(f"Written: {changes.name}", run.result.stdout)
            rows = changes.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(rows, ['"Camera","IpAddress","Head","Column","From","To"',
                                    '"Cam A","127.0.0.10","","Name","Cam A","Cam A renamed"'])
        finally:
            run.close()

    def test_nothing_to_do_asks_nothing(self):
        run = ImportRun(dict(CAMERAS), [])
        try:
            self.assertEqual(run.result.returncode, 2, run.result.stdout)
            self.assertEqual(run.imports, [])
            self.assertNotIn("Type the site name", run.result.stdout)
            self.assertIn("NOTHING TO DO - the cameras already hold every setting in the file", run.text("import.log"))
        finally:
            run.close()


if __name__ == "__main__":
    unittest.main()
