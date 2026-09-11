"""The CSV reader and writer: a file must come back byte for byte, and anything CCT would not have
written must be refused with the line named."""

from __future__ import annotations

import unittest

import camerasettings_csvfile as csvfile

from . import fixtures


class RoundTripTest(unittest.TestCase):
    def test_sample_file_comes_back_identical(self):
        data = fixtures.sample_bytes()
        settings = csvfile.camerasettings_csvfile_parse(data)
        self.assertEqual(csvfile.camerasettings_csvfile_render(settings), data)

    def test_cameras_and_heads_are_grouped(self):
        settings = csvfile.camerasettings_csvfile_parse(fixtures.sample_bytes())
        self.assertEqual(len(settings.cameras), 4)
        self.assertEqual([len(c.analytics) for c in settings.cameras], [1, 1, 3, 1])
        self.assertEqual(settings.cameras[2].line, 7)
        self.assertEqual(settings.mac(settings.cameras[2]), "00-18-85-00-00-03")
        self.assertEqual(settings.value(settings.cameras[0], "Name"), "acc/C1061 - Loading dock")

    def test_real_export_comes_back_identical(self):
        data = fixtures.real_export_bytes()
        if data is None:
            self.skipTest("no site export zip beside the scripts")
        settings = csvfile.camerasettings_csvfile_parse(data)
        self.assertGreater(len(settings.cameras), 0)
        self.assertEqual(csvfile.camerasettings_csvfile_render(settings), data)

    def test_real_export_header_matches_the_column_table(self):
        data = fixtures.real_export_bytes()
        if data is None:
            self.skipTest("no site export zip beside the scripts")
        settings = csvfile.camerasettings_csvfile_parse(data)
        self.assertEqual(settings.header, [fixtures.DEVICE_HEADER, fixtures.ANALYTICS_HEADER])

    def test_lf_only_file_is_written_back_with_lf(self):
        data = b"\xff\xfe" + "\n".join(fixtures.sample_lines()).encode("utf-16-le")
        settings = csvfile.camerasettings_csvfile_parse(data)
        self.assertEqual(settings.newline, "\n")
        self.assertFalse(settings.trailing_newline)
        self.assertEqual(csvfile.camerasettings_csvfile_render(settings), data)


class RefusalTest(unittest.TestCase):
    def refuse(self, data: bytes, fragment: str) -> None:
        with self.assertRaises(csvfile.SettingsFileError) as caught:
            csvfile.camerasettings_csvfile_parse(data, "given.csv")
        self.assertIn(fragment, str(caught.exception))

    def test_no_byte_order_mark(self):
        self.refuse(b"DeviceHeader\tMacAddress\r\n", "byte-order mark")

    def test_device_row_with_wrong_field_count(self):
        lines = fixtures.sample_lines()
        lines[2] = lines[2] + "\textra"
        self.refuse(fixtures.sample_bytes(lines), "line 3: a Device row with 40 fields")

    def test_analytics_before_any_device(self):
        lines = fixtures.sample_lines()
        lines.insert(2, fixtures.analytics_row(1))
        self.refuse(fixtures.sample_bytes(lines), "line 3: an Analytics row before any Device row")

    def test_duplicate_mac(self):
        lines = fixtures.sample_lines()
        lines[4] = fixtures.device_row("00-18-85-00-00-01", "acc/C9 - Twin", "10.20.19.140")
        self.refuse(fixtures.sample_bytes(lines), "line 5: MAC address 00-18-85-00-00-01 already appeared on line 3")

    def test_stray_line(self):
        lines = fixtures.sample_lines()
        lines.insert(4, "")
        self.refuse(fixtures.sample_bytes(lines), "line 5: expected a Device or Analytics row")

    def test_missing_headers(self):
        self.refuse(fixtures.sample_bytes(fixtures.sample_lines()[2:]), "has no DeviceHeader line")
        self.refuse(fixtures.sample_bytes(fixtures.sample_lines()[1:]), "has no DeviceHeader line")
        self.refuse(fixtures.sample_bytes(fixtures.sample_lines()[:1] + fixtures.sample_lines()[2:]), "has no AnalyticsHeader line")


class HelperTest(unittest.TestCase):
    def test_bare_strips_one_matching_pair(self):
        self.assertEqual(csvfile.camerasettings_csvfile_bare('"acc/C1 - x"'), "acc/C1 - x")
        self.assertEqual(csvfile.camerasettings_csvfile_bare("'101909'"), "101909")
        self.assertEqual(csvfile.camerasettings_csvfile_bare('"unbalanced'), '"unbalanced')
        self.assertEqual(csvfile.camerasettings_csvfile_bare(""), "")

    def test_quoted(self):
        self.assertEqual(csvfile.camerasettings_csvfile_quoted("x", '"'), '"x"')
        self.assertEqual(csvfile.camerasettings_csvfile_quoted("x", ""), "x")

    def test_camera_numbers(self):
        numbers = csvfile.camerasettings_csvfile_cameraNumbers
        self.assertEqual(numbers('"acc/C1061 - Loading dock facing the gate (23)"'), ("C1061",))
        self.assertEqual(numbers("acc/C1090, C1091, C1092 - Multisensor"), ("C1090", "C1091", "C1092"))
        self.assertEqual(numbers("acc/C2022 - Back gate CP2"), ("C2022",))
        self.assertEqual(numbers("acc/Back gate"), ())
        self.assertEqual(numbers("c77 - lower case"), ("C77",))
        self.assertEqual(numbers("2.0C-H5A-DO1-IR(5121580)"), ())

    def test_label(self):
        settings = csvfile.camerasettings_csvfile_parse(fixtures.sample_bytes())
        label = csvfile.camerasettings_csvfile_label
        self.assertEqual(label(settings, settings.cameras[0]), "C1061 (10.20.19.128)")
        self.assertEqual(label(settings, settings.cameras[2]), "C1090, C1091, C1092 (10.20.19.132)")
        self.assertEqual(label(settings, settings.cameras[3]), "acc/Back gate (10.20.3.130)")


if __name__ == "__main__":
    unittest.main()
