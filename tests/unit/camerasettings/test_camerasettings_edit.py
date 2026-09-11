"""The editor: rows find their camera three ways, values are checked, every refusal is named, and a
single refusal means nothing is written."""

from __future__ import annotations

import unittest

import camerasettings_csvfile as csvfile
import camerasettings_edit as edit
from camerasettings_sheet import EditSheet, SheetRow

from . import fixtures


def sheet(columns: list[str], *rows: dict[str, str]) -> EditSheet:
    return EditSheet("edits.xlsx", columns, [SheetRow(number, row) for number, row in enumerate(rows, 2)])


class EditApplyTest(unittest.TestCase):
    def setUp(self):
        self.settings = csvfile.camerasettings_csvfile_parse(fixtures.sample_bytes())
        self.before = csvfile.camerasettings_csvfile_render(self.settings)

    def tearDown(self):
        self.assertEqual(csvfile.camerasettings_csvfile_render(self.settings), self.before, "the original was touched")

    def test_rename_by_camera_number(self):
        result = edit.camerasettings_edit_apply(self.settings, sheet(["Camera", "Name"], {"Camera": "c1061", "Name": "acc/C1061 - Front Entrance"}))
        self.assertTrue(result.ok, result.refusals)
        self.assertEqual(len(result.changes), 1)
        change = result.changes[0]
        self.assertEqual((change.camera, change.column, change.head), ("C1061 (10.20.19.128)", "Name", None))
        self.assertEqual((change.old, change.new), ("acc/C1061 - Loading dock", "acc/C1061 - Front Entrance"))
        edited = result.settings.cameras[0].device[result.settings.device_index("Name")]
        self.assertEqual(edited, '"acc/C1061 - Front Entrance"')

    def test_match_by_full_name_by_mac_and_by_ip(self):
        result = edit.camerasettings_edit_apply(self.settings, sheet(
            ["Camera", "Quality"], {"Camera": "ACC/Back gate", "Quality": "8"}))
        self.assertTrue(result.ok, result.refusals)
        self.assertEqual(result.changes[0].camera, "acc/Back gate (10.20.3.130)")

        result = edit.camerasettings_edit_apply(self.settings, sheet(
            ["MacAddress", "Location"], {"MacAddress": "00:18:85:00:00:02", "Location": "acc/Lobby"}))
        self.assertTrue(result.ok, result.refusals)
        self.assertEqual(result.changes[0].mac, "00-18-85-00-00-02")

        result = edit.camerasettings_edit_apply(self.settings, sheet(
            ["IpAddress", "Hostname"], {"IpAddress": "010.020.019.131", "Hostname": "cam-1062"}))
        self.assertTrue(result.ok, result.refusals)
        self.assertEqual(result.changes[0].camera, "C1062 (10.20.19.131)")

    def test_analytics_column_reaches_every_head(self):
        result = edit.camerasettings_edit_apply(self.settings, sheet(
            ["Camera", "TamperSensitivity"], {"Camera": "C1091", "TamperSensitivity": "6"}))
        self.assertTrue(result.ok, result.refusals)
        self.assertEqual([c.head for c in result.changes], [1, 2, 3])
        self.assertEqual(result.changes[0].camera, "C1090, C1091, C1092 (10.20.19.132)")
        position = result.settings.analytics_index("TamperSensitivity")
        self.assertEqual([row[position] for row in result.settings.cameras[2].analytics], ["6", "6", "6"])

    def test_values_are_normalised_and_unchanged_cells_counted(self):
        result = edit.camerasettings_edit_apply(self.settings, sheet(
            ["Camera", "WDREnabled", "Resolution", "Encoding"],
            {"Camera": "C1061", "WDREnabled": "true", "Resolution": "1920x1080", "Encoding": "H264"}))
        self.assertTrue(result.ok, result.refusals)
        self.assertEqual([(c.column, c.new) for c in result.changes], [("Resolution", "1920 x 1080")])
        self.assertEqual(result.already, 2)

    def test_password_needs_the_flag(self):
        rows = sheet(["Camera", "AdminPassword"], {"Camera": "C1061", "AdminPassword": "Test!!2026"})
        refused = edit.camerasettings_edit_apply(self.settings, rows)
        self.assertFalse(refused.ok)
        self.assertIn("--allow-passwords", refused.refusals[0].reason)
        allowed = edit.camerasettings_edit_apply(self.settings, rows, allow_passwords=True)
        self.assertTrue(allowed.ok, allowed.refusals)
        self.assertEqual(allowed.passwords, 1)
        self.assertIn("WARNING", edit.camerasettings_edit_renderLog(allowed, "settings.csv", "edits.xlsx"))

    def test_sheet_level_refusals(self):
        cases = [
            (sheet(["Name"], {"Name": "x"}), "needs exactly one key column"),
            (sheet(["Camera", "MacAddress", "Name"], {"Camera": "C1", "MacAddress": "m", "Name": "x"}), "has MacAddress, Camera"),
            (sheet(["Camera"], {"Camera": "C1061"}), "nothing to change"),
            (sheet(["Camera", "name"], {"Camera": "C1061", "name": "x"}), "did you mean Name"),
            (sheet(["Camera", "Colour"], {"Camera": "C1061", "Colour": "x"}), "no such column"),
            (sheet(["Camera", "Model"], {"Camera": "C1061", "Model": "x"}), "read-only"),
            (sheet(["Camera", "MacAddress"], {"Camera": "C1061", "MacAddress": "x"}), "needs exactly one key column"),
            (sheet(["Camera", "Head"], {"Camera": "C1061", "Head": "2"}), "structure of the file"),
            (sheet(["Camera", "AdminUserName"], {"Camera": "C1061", "AdminUserName": "admin"}), "refuses a different admin user"),
        ]
        for given, fragment in cases:
            result = edit.camerasettings_edit_apply(self.settings, given)
            self.assertFalse(result.ok, fragment)
            self.assertEqual(result.refusals[0].row, 0)
            self.assertIn(fragment, result.refusals[0].reason)
            self.assertEqual(result.changes, [])

    def test_row_level_refusals_keep_going_and_write_nothing(self):
        lines = fixtures.sample_lines()
        lines += [fixtures.device_row("00-18-85-00-00-05", "acc/C1061 - The twin", "10.20.19.140"), fixtures.analytics_row(1)]
        settings = csvfile.camerasettings_csvfile_parse(fixtures.sample_bytes(lines))
        result = edit.camerasettings_edit_apply(settings, sheet(
            ["Camera", "Name", "Quality"],
            {"Camera": "C1062", "Name": "acc/C1062 - Good", "Quality": ""},
            {"Camera": "C9999", "Name": "acc/C9999 - Nobody", "Quality": ""},
            {"Camera": "C1061", "Name": "acc/C1061 - Which one", "Quality": ""},
            {"Camera": "C1090", "Name": "", "Quality": "21"},
            {"Camera": "", "Name": "x", "Quality": ""},
            {"Camera": "C1062", "Name": "acc/C1062 - Again", "Quality": ""},
        ))
        self.assertFalse(result.ok)
        reasons = [(r.row, r.reason) for r in result.refusals]
        self.assertEqual(reasons[0][0], 3)
        self.assertIn("no camera matches Camera C9999", reasons[0][1])
        self.assertIn("matches more than one camera: C1061 (10.20.19.128); C1061 (10.20.19.140). Use the MacAddress", reasons[1][1])
        self.assertIn("Quality must be at most 20, not 21", reasons[2][1])
        self.assertIn("row 6 has no Camera", reasons[3][1])
        self.assertIn("already appeared on row 2", reasons[4][1])
        self.assertEqual(len(result.changes), 1)
        log = edit.camerasettings_edit_renderLog(result, "settings.csv", "edits.xlsx")
        self.assertIn("REFUSED - nothing was written", log)
        self.assertIn("CHANGES THAT WOULD HAVE BEEN MADE", log)
        self.assertIn("Refused            : 5", log)

    def test_log_reads_as_a_record(self):
        result = edit.camerasettings_edit_apply(self.settings, sheet(
            ["Camera", "Name", "Quality"],
            {"Camera": "C1061", "Name": "acc/C1061 - Front", "Quality": "8"},
            {"Camera": "C1062", "Name": "acc/C1062 - Rear", "Quality": ""},
        ))
        log = edit.camerasettings_edit_renderLog(result, "settings.csv", "renames.xlsx")
        self.assertIn("Edit log - renames.xlsx applied to settings.csv", log)
        self.assertIn("Cameras changed    : 2", log)
        self.assertIn("Changes            : 3   (Name 2, Quality 1)", log)
        self.assertIn("  C1061 (10.20.19.128)                      Name                        'acc/C1061 - Loading dock' -> 'acc/C1061 - Front'", log)
        self.assertIn("Quality                     '6' -> '8'", log)
        self.assertNotIn("REFUSED", log)


if __name__ == "__main__":
    unittest.main()
