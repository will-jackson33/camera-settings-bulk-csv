"""The generated PowerShell column table: it names every column the Python table types, and the
copy inside each .bat at the root is the current one."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import camerasettings_columns as columns  # noqa: E402
import columns_block  # noqa: E402


class ColumnsBlockTest(unittest.TestCase):
    def setUp(self):
        self.lines = columns_block.columns_block_render()
        self.text = "\n".join(self.lines)

    def test_every_typed_column_is_in_the_kind_table(self):
        for column in columns.DEVICE_COLUMNS + columns.ANALYTICS_COLUMNS:
            if column.name and column.kind is not columns.ColumnKind.TEXT:
                self.assertIn(f"$colKind['{column.name}'] = ", self.text, column.name)

    def test_the_shapes_a_reader_relies_on(self):
        self.assertIn("$colQuote['Name'] = '\"'", self.text)
        self.assertIn("$colQuote['SerialNumber'] = ''''", self.text)
        self.assertIn("$colKind['Quality'] = 'int|1|20'", self.text)
        self.assertIn("$colKind['ImageRate'] = 'int|1|'", self.text)
        self.assertIn("$colKind['Encoding'] = 'choice|JPEG|MPEG4|H264|H265'", self.text)
        self.assertIn("$colKind['CameraMode'] = 'choice|Full Feature|High Framerate|", self.text)
        self.assertIn("$colRole['MacAddress'] = 'key'", self.text)
        self.assertIn("$colRole['AdminPassword'] = 'password'", self.text)
        self.assertIn("$colRole['SerialNumber'] = 'identity'", self.text)
        self.assertIn("$colWords['AnalyticsSceneMode'] = @{ '0' = 'Outdoor'; '1' = 'Large Indoor Area';", self.text)
        self.assertNotIn("$colRole['Name']", self.text)

    def test_only_single_quoted_powershell_literals(self):
        # Data only: nothing here may run code when the block is dot-sourced on a site laptop.
        for line in self.lines:
            if line.startswith("#"):
                continue
            self.assertTrue(re.fullmatch(r"\$col\w+(\[('[^']*'|'[^']*''[^']*')\])? = (@\{\}|@\{ .* \}|'.*')", line), line)

    def test_every_root_bat_holds_the_current_block(self):
        self.assertEqual(columns_block.columns_block_check(), [])


if __name__ == "__main__":
    unittest.main()
