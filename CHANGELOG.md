# Changelog

The version is the `VERSION=` line near the top of each script, printed in its banner and its
window title, and `__version__` in `camerasettings_main.py`; the checker refuses a mismatch
between the three. Patch for a fix, minor for something new that breaks nothing, major for
something that breaks. Every commit in this repository is a version bump and is named for it,
with its entry here in the same commit.

## 1.0.0 — 2026-09-11

The first release built to be handed to a site. Everything before it carried no number.

### Added
- The export zip holds `settings.csv` - one comma-separated row per camera, in CCT's column
  order, that Excel opens as it is - and `analytics.csv`, one row per camera head with the coded
  values shown as words. CCT's own file travels beside them as `backup`, untouched and without
  an extension, so a double-click asks what to open it with rather than handing it to Excel.
- The import reads either shape, told apart from the bytes: an export made before this release
  still imports unchanged, and a file Excel saved as plain CSV, CSV UTF-8 or Unicode Text all
  read.
- The import's form asks for the rollback file - the backup file from the export zip is offered
  when it sits beside the dropped file - or blank to export one now.
- Every edited cell is checked before anything is written: `TRUE` is `True`, `1920x1080` is
  `1920 x 1080`, `Outdoor` is `0`. A cell the column cannot read is left as it is on the camera
  and named on screen and in `camera.log`; the rest of the file goes ahead.
- The plan lists each change as three lines - who, from, to - and offers the change list as a
  CSV beside the script, one y/N question. `changes.csv` is in the zip either way.
- A version number, in both banners.
- `README.md` is the user guide - every step, every screen, every stop and what to do about it -
  and `ARCHITECTURE.md` is the maintainer's document beside it.

### Changed
- The import writes only to the cameras that change. CCT is handed a file holding just those
  cameras, built from the rollback's own rows with only the changed cells applied, and address
  ranges that never include a camera that is not changing - neighbours share a run, and a run is
  split wherever an unchanged camera sits between two that change. The proof export walks the
  same ranges. Two renames on a 97-camera subnet went from about two minutes and 97 cameras
  written to two short runs and two cameras.
- The two scripts are `1 export settings.bat` and `2 import settings.bat`, numbered in the order
  they are run. Nothing else at the root is for a technician.
- `camera.log` in the import zip carries one table per phase and says how many cameras were
  written to and how many CCT runs it took.
- The two files nobody should open in Excel carry no extension: `backup` in the export zip and
  `rollback` in the import zip. A double-click asks what to open them with instead of handing the
  file that puts a site back to the one program that breaks it.

### Removed
- `edit settings.bat` and `compare settings.bat`. The readable file is edited directly, and the
  import compares it against the rollback and shows the plan itself. Their Python stays under
  `src\camerasettings\` as the desk tool and the reference reading of CCT's format.
