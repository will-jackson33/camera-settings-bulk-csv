"""The compare tool: a known edit produces exactly its entries, anything import would not apply is
flagged, passwords never reach a report, and the two renderings carry the same verdict."""

from __future__ import annotations

import copy
import unittest

import camerasettings_compare as compare
import camerasettings_csvfile as csvfile

from . import fixtures


def edited_copy(settings: csvfile.SettingsFile) -> csvfile.SettingsFile:
    return copy.deepcopy(settings)


def set_device(settings: csvfile.SettingsFile, camera: csvfile.SettingsCamera, column: str, value: str) -> None:
    quote = {"Name": '"', "Location": '"', "SerialNumber": "'", "FirmwareVersion": '"'}.get(column, "")
    camera.device[settings.device_index(column)] = f"{quote}{value}{quote}"


class KnownEditTest(unittest.TestCase):
    def setUp(self):
        self.original = csvfile.camerasettings_csvfile_parse(fixtures.sample_bytes())
        self.edited = edited_copy(self.original)
        cams = self.edited.cameras
        set_device(self.edited, cams[0], "Name", "acc/C1061 - Loading dock (east)")
        set_device(self.edited, cams[1], "Name", "acc/C1062 - Lobby path")
        set_device(self.edited, cams[2], "Name", "acc/C1090, C1091, C1092 - Multisensor, roof")
        set_device(self.edited, cams[0], "Quality", "8")
        set_device(self.edited, cams[1], "Quality", "8")
        cams[2].analytics[1][self.edited.analytics_index("TamperSensitivity")] = "6"
        del cams[3]  # the camera with no C-number is gone from the edited file
        self.report = compare.camerasettings_compare_diff(self.original, self.edited, "settings.csv", "settings.edited.csv")

    def test_every_difference_is_listed_once_and_nothing_else(self):
        listed = sorted((c.camera, c.column, c.head, c.old, c.new) for c in self.report.changes)
        self.assertEqual(listed, sorted([
            ("C1061 (10.20.19.128)", "Name", None, "acc/C1061 - Loading dock", "acc/C1061 - Loading dock (east)"),
            ("C1062 (10.20.19.131)", "Name", None, "acc/C1062 - Path to the lobby", "acc/C1062 - Lobby path"),
            ("C1090, C1091, C1092 (10.20.19.132)", "Name", None, "acc/C1090, C1091, C1092 - Multisensor", "acc/C1090, C1091, C1092 - Multisensor, roof"),
            ("C1061 (10.20.19.128)", "Quality", None, "6", "8"),
            ("C1062 (10.20.19.131)", "Quality", None, "10", "8"),
            ("C1090, C1091, C1092 (10.20.19.132)", "TamperSensitivity", 2, "8", "6"),
        ]))
        self.assertEqual(self.report.per_column(), [("Name", 3), ("Quality", 2), ("TamperSensitivity", 1)])
        self.assertEqual(self.report.cameras_changed, 3)

    def test_missing_camera_makes_it_unsafe(self):
        self.assertEqual(self.report.only_original, ["acc/Back gate (10.20.3.130)"])
        self.assertFalse(self.report.ok)
        self.assertEqual(self.report.verdict(), "NOT SAFE TO IMPORT - 1 cameras missing from the edited file")

    def test_text_render(self):
        text = compare.camerasettings_compare_renderText(self.report)
        self.assertIn("Verdict            : NOT SAFE TO IMPORT", text)
        self.assertIn("Cameras            : 4 in the original, 3 in the edited file, 3 changed", text)
        self.assertIn("Changes            : 6   (Name 3, Quality 2, TamperSensitivity 1)", text)
        self.assertIn("MISSING FROM THE EDITED FILE", text)
        self.assertIn("  acc/Back gate (10.20.3.130)", text)
        self.assertIn("Name (3)\n  C1061 (10.20.19.128)", text)
        self.assertIn("head 2  '8' -> '6'", text)

    def test_html_render(self):
        page = compare.camerasettings_compare_renderHtml(self.report)
        self.assertIn('<div class="verdict bad">NOT SAFE TO IMPORT', page)
        self.assertIn("<h2>Name (3)</h2>", page)
        self.assertIn("<h2>TamperSensitivity (1)</h2>", page)
        self.assertIn("<ins> (east)</ins>", page)
        self.assertIn("<del>10</del>", page)
        self.assertIn("<th>Head</th>", page)
        self.assertIn("Missing from the edited file", page)


class SafePairTest(unittest.TestCase):
    def setUp(self):
        self.original = csvfile.camerasettings_csvfile_parse(fixtures.sample_bytes())

    def test_identical_files(self):
        report = compare.camerasettings_compare_diff(self.original, edited_copy(self.original))
        self.assertTrue(report.ok)
        self.assertEqual(report.changes, [])
        self.assertEqual(report.verdict(), "NOTHING TO IMPORT - the two files hold the same settings")

    def test_only_applied_columns_changed(self):
        edited = edited_copy(self.original)
        set_device(edited, edited.cameras[0], "Location", "acc/Car park")
        report = compare.camerasettings_compare_diff(self.original, edited)
        self.assertTrue(report.ok)
        self.assertEqual(report.verdict(), "SAFE TO IMPORT - 1 changes on 1 cameras, all in columns import applies")
        self.assertIn('<div class="verdict">SAFE TO IMPORT', compare.camerasettings_compare_renderHtml(report))

    def test_password_is_applied_but_never_shown(self):
        edited = edited_copy(self.original)
        set_device(edited, edited.cameras[0], "AdminPassword", "Test!!2026")
        report = compare.camerasettings_compare_diff(self.original, edited)
        self.assertTrue(report.ok)
        self.assertEqual((report.changes[0].column, report.changes[0].old, report.changes[0].new), ("AdminPassword", "", "(set)"))
        self.assertNotIn("Test!!2026", compare.camerasettings_compare_renderText(report))
        self.assertNotIn("Test!!2026", compare.camerasettings_compare_renderHtml(report))


class UnsafePairTest(unittest.TestCase):
    def setUp(self):
        self.original = csvfile.camerasettings_csvfile_parse(fixtures.sample_bytes())

    def test_read_only_and_admin_user_changes_are_forbidden(self):
        edited = edited_copy(self.original)
        set_device(edited, edited.cameras[0], "Model", "9C-H4A-3MH-180")
        set_device(edited, edited.cameras[1], "AdminUserName", "admin")
        report = compare.camerasettings_compare_diff(self.original, edited)
        self.assertFalse(report.ok)
        self.assertEqual([(c.camera, c.column) for c in report.forbidden],
                         [("C1061 (10.20.19.128)", "Model"), ("C1062 (10.20.19.131)", "AdminUserName")])
        self.assertEqual(report.changes, [])
        text = compare.camerasettings_compare_renderText(report)
        self.assertIn("CHANGES IMPORT IGNORES OR REFUSES", text)
        self.assertIn("2 changes in columns import ignores or refuses", text)

    def test_head_count_and_column_set_are_structure(self):
        edited = edited_copy(self.original)
        del edited.cameras[2].analytics[2]
        report = compare.camerasettings_compare_diff(self.original, edited)
        self.assertEqual(report.structure, ["C1090, C1091, C1092 (10.20.19.132): 3 heads in the original, 2 in the edited file"])
        self.assertFalse(report.ok)

        narrower = fixtures.sample_lines()
        narrower[0] = narrower[0] + "\tNewColumn"
        narrower[2:] = [ln + ("\t" if ln.startswith("Device") else "") for ln in narrower[2:]]
        other = csvfile.camerasettings_csvfile_parse(fixtures.sample_bytes(narrower))
        report = compare.camerasettings_compare_diff(self.original, other)
        self.assertIn("do not have the same columns", report.structure[0])

    def test_extra_camera_in_the_edited_file(self):
        lines = fixtures.sample_lines() + [fixtures.device_row("00-18-85-00-00-09", "acc/C9 - New", "10.20.3.140"), fixtures.analytics_row(1)]
        edited = csvfile.camerasettings_csvfile_parse(fixtures.sample_bytes(lines))
        report = compare.camerasettings_compare_diff(self.original, edited)
        self.assertEqual(report.only_edited, ["C9 (10.20.3.140)"])
        self.assertFalse(report.ok)


class MarkTest(unittest.TestCase):
    def test_changed_characters_are_wrapped_and_escaped(self):
        old, new = compare._mark("acc/C1 <Front>", "acc/C1 <Rear>")
        self.assertIn("<del>", old)
        self.assertIn("<ins>", new)
        self.assertNotIn("<ins>", old)
        self.assertNotIn("<del>", new)
        strip = lambda marked: marked.replace("<del>", "").replace("</del>", "").replace("<ins>", "").replace("</ins>", "")  # noqa: E731
        self.assertEqual(strip(old), "acc/C1 &lt;Front&gt;")
        self.assertEqual(strip(new), "acc/C1 &lt;Rear&gt;")

    def test_unchanged_prefix_is_not_marked(self):
        old, new = compare._mark("acc/C1061 - Loading dock (23)", "acc/C1061 - Loading dock")
        self.assertTrue(old.startswith("acc/C1061 - Loading dock"))
        self.assertEqual(new, "acc/C1061 - Loading dock")
        self.assertIn("<del>", old)


if __name__ == "__main__":
    unittest.main()
