"""The desk tools for CCT's own file: apply an edit sheet to a settings file, or compare two.

    .venv\\Scripts\\python src\\camerasettings\\camerasettings_main.py edit "backup" edits.xlsx
    .venv\\Scripts\\python src\\camerasettings\\camerasettings_main.py compare "backup" edited.csv

The site tools do both jobs themselves - the export writes a readable file a person edits
in Excel and the import compares it against the rollback - so these stay for the desk and as the
reference reading of the format the tests hold the scripts to. Exit codes: 0 done, 1 refused or
different (the log says why), 2 the inputs could not be read. Outputs land beside the settings file
and are never overwritten - a second run gets _1, _2, as the export does with its zips.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import camerasettings_compare as compare
import camerasettings_csvfile as csvfile
import camerasettings_edit as edit
import camerasettings_sheet as sheet

# The same number the two scripts carry in their VERSION= line; tests/check_bat.py holds them together.
__version__ = "1.0.5"


def camerasettings_main_freeName(path: Path) -> Path:
    """The path itself if nothing is there, else the first of name_1, name_2, ... that is free."""
    if not path.exists():
        return path
    for n in range(1, 1000):
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"a thousand files named like {path.name} already exist here")


def _settings_and_sheet(first: Path, second: Path) -> tuple[Path, Path]:
    """Dropping two files on a .bat hands them over in no particular order; the CSV is the settings file."""
    if second.suffix.lower() == ".csv" and first.suffix.lower() != ".csv":
        return second, first
    return first, second


def camerasettings_main_edit(args: argparse.Namespace) -> int:
    settings_path, sheet_path = _settings_and_sheet(Path(args.settings), Path(args.sheet))
    try:
        settings = csvfile.camerasettings_csvfile_read(settings_path)
    except (OSError, csvfile.SettingsFileError) as error:
        print(f"Cannot read the settings file: {error}")
        return 2
    try:
        edits = sheet.camerasettings_sheet_read(sheet_path, args.worksheet)
    except (OSError, sheet.SheetError) as error:
        print(f"Cannot read the edit sheet: {error}")
        return 2

    result = edit.camerasettings_edit_apply(settings, edits, allow_passwords=args.allow_passwords)
    log_text = edit.camerasettings_edit_renderLog(result, settings_path.name, sheet_path.name)
    log_path = camerasettings_main_freeName(settings_path.with_name("edit.log"))
    log_path.write_text(log_text, encoding="utf-8")
    print(log_text)
    if not result.ok:
        print(f"Nothing was written. The refusals are in {log_path}")
        return 1
    out_path = camerasettings_main_freeName(settings_path.with_name(settings_path.stem + ".edited.csv"))
    csvfile.camerasettings_csvfile_write(result.settings, out_path)
    print(f"Edited file : {out_path}")
    print(f"Edit log    : {log_path}")
    print("Next        : compare the original against the edited file before anything is imported.")
    return 0


def _original_and_edited(first: Path, second: Path) -> tuple[Path, Path]:
    """The original comes first; a drop may reverse them, and the edited copy says so in its name."""
    if ".edited" in first.name.lower() and ".edited" not in second.name.lower():
        return second, first
    return first, second


def camerasettings_main_compare(args: argparse.Namespace) -> int:
    original_path, edited_path = _original_and_edited(Path(args.original), Path(args.edited))
    try:
        original = csvfile.camerasettings_csvfile_read(original_path)
        edited = csvfile.camerasettings_csvfile_read(edited_path)
    except (OSError, csvfile.SettingsFileError) as error:
        print(f"Cannot read a settings file: {error}")
        return 2
    report = compare.camerasettings_compare_diff(original, edited, original_path.name, edited_path.name)
    text = compare.camerasettings_compare_renderText(report)
    log_path = camerasettings_main_freeName(edited_path.with_name("compare.log"))
    html_path = camerasettings_main_freeName(edited_path.with_name("compare.html"))
    log_path.write_text(text, encoding="utf-8")
    html_path.write_text(compare.camerasettings_compare_renderHtml(report), encoding="utf-8")
    print(text)
    print(f"Report      : {html_path}")
    print(f"As text     : {log_path}")
    return 0 if report.ok else 1


def camerasettings_main_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="camera-settings", description="Edit and compare CCT settings files.")
    parser.add_argument("--version", action="version", version=f"camera-settings {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    edit_command = commands.add_parser("edit", help="apply an edit sheet to a settings.csv")
    edit_command.add_argument("settings", help="the settings.csv from an export, or the sheet - either order")
    edit_command.add_argument("sheet", help="the .xlsx, .csv or .tsv of edits, or the settings file - either order")
    edit_command.add_argument("--worksheet", help="the worksheet to read, when it is not the first")
    edit_command.add_argument("--allow-passwords", action="store_true",
                              help="let the sheet set AdminPassword or SecondaryAdminPassword")
    edit_command.set_defaults(run=camerasettings_main_edit)
    compare_command = commands.add_parser("compare", help="what differs between an export and its edited copy")
    compare_command.add_argument("original", help="the settings.csv from the export")
    compare_command.add_argument("edited", help="the edited copy - either order when one is named .edited.")
    compare_command.set_defaults(run=camerasettings_main_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = camerasettings_main_parser().parse_args(argv)
    result: int = args.run(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
