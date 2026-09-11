"""The column table and the value normaliser: every kind accepts what a person would type and
refuses the rest with a sentence that names the column."""

from __future__ import annotations

import unittest

import camerasettings_columns as columns


class TableTest(unittest.TestCase):
    def test_every_g0101_column_is_present_in_order(self):
        self.assertEqual(len(columns.DEVICE_COLUMNS), 39)
        self.assertEqual(len(columns.ANALYTICS_COLUMNS), 12)
        self.assertEqual(columns.DEVICE_COLUMNS[11].name, "IpAddress")
        self.assertEqual(columns.DEVICE_COLUMNS[16].role, columns.ColumnRole.PASSWORD)
        self.assertEqual(columns.ANALYTICS_COLUMNS[-1].name, "")

    def test_by_name_skips_the_unnamed_placeholder(self):
        table = columns.camerasettings_columns_byName()
        self.assertNotIn("", table)
        self.assertEqual(table["Name"].quote, '"')
        self.assertEqual(table["SerialNumber"].quote, "'")
        self.assertEqual(table["Quality"].high, 20)


class NormalizeTest(unittest.TestCase):
    def setUp(self):
        self.table = columns.camerasettings_columns_byName()

    def ok(self, column: str, given: str, expected: str) -> None:
        self.assertEqual(columns.camerasettings_columns_normalize(self.table[column], given), expected)

    def refuse(self, column: str, given: str, fragment: str) -> None:
        with self.assertRaises(ValueError) as caught:
            columns.camerasettings_columns_normalize(self.table[column], given)
        self.assertIn(column, str(caught.exception))
        self.assertIn(fragment, str(caught.exception))

    def test_bool(self):
        self.ok("WDREnabled", "TRUE", "True")
        self.ok("WDREnabled", " false ", "False")
        self.refuse("WDREnabled", "yes", "True or False")

    def test_int_with_bounds(self):
        self.ok("Quality", "6", "6")
        self.ok("Quality", "020", "20")
        self.refuse("Quality", "21", "at most 20")
        self.refuse("Quality", "0", "at least 1")
        self.refuse("ImageRate", "25.0", "whole number")
        self.ok("TamperTriggerDelay", "0", "0")

    def test_float(self):
        self.ok("TamperThreshold", "0.35", "0.35")
        self.refuse("TamperThreshold", "high", "a number")

    def test_ip(self):
        self.ok("IpAddress", "010.020.003.128", "10.20.3.128")
        self.refuse("SubnetMask", "255.255.256.0", "address like")
        self.refuse("DefaultGateway", "10.20.3", "address like")

    def test_resolution(self):
        self.ok("Resolution", "1920x1080", "1920 x 1080")
        self.ok("Resolution", " 2592 X 1944 ", "2592 x 1944")
        self.refuse("Resolution", "1080p", "width x height")

    def test_choice_is_case_insensitive_and_canonical(self):
        self.ok("Encoding", "h265", "H265")
        self.ok("CameraMode", "full feature", "Full Feature")
        self.ok("NtpServerModeDhcp", "manual", "Manual")
        self.ok("VideoAnalyticsMode", "2", "2")
        self.refuse("Encoding", "H266", "one of JPEG, MPEG4, H264, H265")
        self.refuse("AnalyticsSceneMode", "5", "one of")

    def test_text_refuses_what_breaks_the_row(self):
        self.ok("Name", "  acc/C1061 - Loading dock  ", "acc/C1061 - Loading dock")
        self.refuse("Name", 'acc/C1 "the" way', "cannot contain the \" character")
        self.refuse("Location", "a\tb", "a tab")
        self.refuse("Hostname", "a\nb", "a line break")


if __name__ == "__main__":
    unittest.main()
