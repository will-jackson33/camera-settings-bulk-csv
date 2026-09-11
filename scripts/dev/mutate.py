"""Mutation testing for the batch scripts: break one rule at a time and watch a test fail.

Every case names a gate or a guarantee the script is supposed to hold. A MISSED line means the
tests do not cover that gate - the fix is a new test, not a shrug. The scripts are copied to a
temp file and the tests are pointed at the copy through CAMERA_SETTINGS_BAT and
CAMERA_SETTINGS_IMPORT_BAT, so the real files are never rewritten.

    .venv\\Scripts\\python scripts\\dev\\mutate.py            every case
    .venv\\Scripts\\python scripts\\dev\\mutate.py import     just the import ones
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


@dataclass(frozen=True)
class Mutation:
    script: str  # the .bat at the project root
    env: str  # the environment variable the tests read it from
    tests: str  # what to run
    what: str  # the gate this breaks, in plain words
    old: str
    new: str = ""


IMPORT_TESTS = "tests/integration/test_import_stub.py"
EXPORT_TESTS = "tests/integration/test_export_stub.py"

MUTATIONS = (
    Mutation("import.bat", "CAMERA_SETTINGS_IMPORT_BAT", IMPORT_TESTS,
             "the stop when a camera in the file did not answer",
             'if not "%MISSING%"=="0" goto missing_cameras\r\n'),
    Mutation("import.bat", "CAMERA_SETTINGS_IMPORT_BAT", IMPORT_TESTS,
             "the site-name confirmation",
             'if "%TYPED%"=="%SITE%" set "MATCHED=yes"', 'set "MATCHED=yes"'),
    Mutation("import.bat", "CAMERA_SETTINGS_IMPORT_BAT", IMPORT_TESTS,
             "the ROTATE gate in front of a password change",
             'if "%TYPED%"=="ROTATE" set "MATCHED=yes"', 'set "MATCHED=yes"'),
    Mutation("import.bat", "CAMERA_SETTINGS_IMPORT_BAT", IMPORT_TESTS,
             "the rollback export taken before anything is written",
             'set "PHASE=rollback"\r\nset "PHASETOTAL=%RUNCOUNT%"\r\nset "RUNNO=0"\r\npushd "%STAGE%"\r\n'
             'for /f "usebackq tokens=1,2" %%A in ("runlist-rollback.txt") do call :export_range %%A %%B\r\npopd\r\n'),
    Mutation("import.bat", "CAMERA_SETTINGS_IMPORT_BAT", IMPORT_TESTS,
             "the proof export taken after the import",
             'set "PHASE=after"\r\nset "PHASETOTAL=%AFTERRUNS%"\r\nset "RUNNO=0"\r\npushd "%STAGE%"\r\n'
             'for /f "usebackq tokens=1,2" %%A in ("runlist-after.txt") do call :export_range %%A %%B\r\npopd\r\n'),
    Mutation("import.bat", "CAMERA_SETTINGS_IMPORT_BAT", IMPORT_TESTS,
             "the narrowing - CCT is handed only the cameras that change",
             "if ($narrow.Order.Count -gt 0) { Write-Native $narrow (Join-Path $out 'settings.csv') }",
             "Write-Native $wanted (Join-Path $out 'settings.csv')"),
    Mutation("import.bat", "CAMERA_SETTINGS_IMPORT_BAT", IMPORT_TESTS,
             "the run split at a camera that is not changing",
             "$importRuns = Ranges $now $avoid", "$importRuns = Ranges $now @{}"),
    Mutation("import.bat", "CAMERA_SETTINGS_IMPORT_BAT", IMPORT_TESTS,
             "a cell the column cannot read is never written to the camera",
             "if (-not $norm.Ok) { $badCount++; $bad += ('  ' + $label + '   ' + $column + \"   '\" + $new + \"'\"); $bad += ('      ' + $norm.Reason); continue }\r\n"
             "            $new = $norm.Value\r\n",
             "if (-not $norm.Ok) { $badCount++; $bad += ('  ' + $label + '   ' + $column + \"   '\" + $new + \"'\"); $bad += ('      ' + $norm.Reason) }\r\n"
             "            if ($norm.Ok) { $new = $norm.Value }\r\n"),
    Mutation("import.bat", "CAMERA_SETTINGS_IMPORT_BAT", IMPORT_TESTS,
             "the exit code surviving endlocal",
             "endlocal & exit /b %RC%", "endlocal\r\nexit /b %RC%"),
    Mutation("export.bat", "CAMERA_SETTINGS_BAT", EXPORT_TESTS,
             "the web-port probe that keeps CCT off addresses it cannot log in to",
             "if ([int]$candCount[$bs] -gt 0) { $runlist +=", "if ($true) { $runlist +="),
    Mutation("export.bat", "CAMERA_SETTINGS_BAT", EXPORT_TESTS,
             "the merge that keeps one header block",
             ".EndsWith('Header')) { if (-not $headerDone) { $merged.Add($ln) } }",
             ".EndsWith('Header')) { $merged.Add($ln) }"),
)


def run(mutation: Mutation, work: Path) -> bool:
    """Apply one mutation to a copy and report whether the tests caught it."""
    source = ROOT / mutation.script
    text = source.read_bytes().decode("ascii")
    if text.count(mutation.old) != 1:
        print(f"STALE   - {mutation.what}: the text it breaks is not in {mutation.script} exactly once")
        return False
    target = work / mutation.script
    target.write_bytes(text.replace(mutation.old, mutation.new).encode("ascii"))
    env = {**os.environ, mutation.env: str(target)}
    result = subprocess.run([str(PYTHON), "-m", "pytest", mutation.tests, "-q", "-x"],
                            cwd=str(ROOT), env=env, capture_output=True, text=True)
    caught = result.returncode != 0
    print(f"{'CAUGHT' if caught else 'MISSED'}  - {mutation.what}")
    if not caught:
        print("          no test failed - that gate is unproven")
    return caught


def main(argv: list[str]) -> int:
    wanted = argv[0].lower() if argv else ""
    chosen = [m for m in MUTATIONS if not wanted or wanted in m.script]
    if not chosen:
        print(f"no mutations match {wanted!r}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        results = [run(m, Path(tmp)) for m in chosen]
    missed = results.count(False)
    print()
    print(f"{len(results) - missed} of {len(results)} caught")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
