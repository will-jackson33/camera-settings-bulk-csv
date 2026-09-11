"""The edit-sheet reader: Excel and text files come back as the same table of typed text."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

import camerasettings_sheet as sheet


def write_xlsx(path: Path, rows: list[list[object]], second_sheet: list[list[object]] | None = None) -> None:
    book = Workbook()
    first = book.active
    for row in rows:
        first.append(row)
    if second_sheet is not None:
        other = book.create_sheet("Renames")
        for row in second_sheet:
            other.append(row)
    book.save(path)


class SheetReadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_xlsx_cells_become_typed_text(self):
        path = self.dir / "edits.xlsx"
        write_xlsx(path, [
            ["Camera", "Name", "Quality", "WDREnabled", "Date", None],
            ["C1061", "acc/C1061 - Front Entrance", 6, True, datetime.datetime(2026, 9, 9, 12, 0), None],
            [None, None, None, None, None, None],
            ["C1062", None, 8.0, False, None, None],
            ["C1063", "  padded  ", 7.5, None, None, None],
        ])
        result = sheet.camerasettings_sheet_read(path)
        self.assertEqual(result.source, "edits.xlsx")
        self.assertEqual(result.columns, ["Camera", "Name", "Quality", "WDREnabled", "Date"])
        self.assertEqual([r.number for r in result.rows], [2, 4, 5])
        self.assertEqual(result.rows[0].values, {"Camera": "C1061", "Name": "acc/C1061 - Front Entrance", "Quality": "6",
                                                 "WDREnabled": "True", "Date": "2026-09-09 12:00:00"})
        self.assertEqual(result.rows[1].values, {"Camera": "C1062", "Name": "", "Quality": "8", "WDREnabled": "False", "Date": ""})
        self.assertEqual(result.rows[2].values["Name"], "padded")
        self.assertEqual(result.rows[2].values["Quality"], "7.5")

    def test_named_worksheet(self):
        path = self.dir / "book.xlsx"
        write_xlsx(path, [["Ignore"], ["x"]], second_sheet=[["MacAddress", "Location"], ["00-18-85-00-00-01", "Lobby"]])
        result = sheet.camerasettings_sheet_read(path, worksheet="Renames")
        self.assertEqual(result.columns, ["MacAddress", "Location"])
        with self.assertRaises(sheet.SheetError) as caught:
            sheet.camerasettings_sheet_read(path, worksheet="Missing")
        self.assertIn("no worksheet named Missing", str(caught.exception))

    def test_csv_with_utf8_bom_and_short_rows(self):
        path = self.dir / "edits.csv"
        path.write_bytes(b"\xef\xbb\xbfIpAddress,Name,Location\r\n10.20.3.128,\"acc/C1, with comma\"\r\n10.20.3.129,,\r\n")
        result = sheet.camerasettings_sheet_read(path)
        self.assertEqual(result.rows[0].values, {"IpAddress": "10.20.3.128", "Name": "acc/C1, with comma", "Location": ""})
        self.assertEqual(len(result.rows), 2)

    def test_tsv_in_utf16(self):
        path = self.dir / "edits.tsv"
        path.write_bytes(b"\xff\xfe" + "Camera\tName\nC5\tacc/C5 - Café\n".encode("utf-16-le"))
        result = sheet.camerasettings_sheet_read(path)
        self.assertEqual(result.rows[0].values["Name"], "acc/C5 - Café")

    def test_refusals(self):
        with self.assertRaises(sheet.SheetError) as caught:
            sheet.camerasettings_sheet_read(self.dir / "nothing.xlsx")
        self.assertIn("does not exist", str(caught.exception))

        path = self.dir / "twice.csv"
        path.write_text("Camera,Name,Name\nC1,a,b\n", encoding="utf-8")
        with self.assertRaises(sheet.SheetError) as caught:
            sheet.camerasettings_sheet_read(path)
        self.assertIn("names a column twice: Name", str(caught.exception))

        empty = self.dir / "empty.csv"
        empty.write_text("", encoding="utf-8")
        with self.assertRaises(sheet.SheetError) as caught:
            sheet.camerasettings_sheet_read(empty)
        self.assertIn("no header row", str(caught.exception))

        other = self.dir / "edits.docx"
        other.write_text("x", encoding="utf-8")
        with self.assertRaises(sheet.SheetError) as caught:
            sheet.camerasettings_sheet_read(other)
        self.assertIn("not .docx", str(caught.exception))


class CellTextTest(unittest.TestCase):
    def test_kinds(self):
        text = sheet.camerasettings_sheet_cellText
        self.assertEqual(text(None), "")
        self.assertEqual(text(True), "True")
        self.assertEqual(text(0), "0")
        self.assertEqual(text(25.0), "25")
        self.assertEqual(text(0.35), "0.35")
        self.assertEqual(text(datetime.date(2026, 9, 9)), "2026-09-09")
        self.assertEqual(text(" H264 "), "H264")


if __name__ == "__main__":
    unittest.main()
