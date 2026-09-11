"""The column table as PowerShell, generated from camerasettings_columns so the .bat files and the
Python side can never disagree about what a column holds.

    .venv\\Scripts\\python scripts\\dev\\columns_block.py            print the block
    .venv\\Scripts\\python scripts\\dev\\columns_block.py --write    rewrite it between the COLS markers of every root .bat
    .venv\\Scripts\\python scripts\\dev\\columns_block.py --check    exit 1 when any root .bat holds a stale copy

The block is data only - four hashtables - and the test suite runs --check, so a column added in
Python without a regeneration fails the build rather than the next site.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "camerasettings"))

import camerasettings_columns as columns  # noqa: E402

START = "###PSCOLS###"
END = "###ENDCOLS###"


def _ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _kind(column: columns.SettingsColumn) -> str:
    """kind|arg|arg - the choices for a choice, the bounds for an int, nothing for the rest."""
    if column.kind is columns.ColumnKind.CHOICE:
        return "|".join(("choice", *column.choices))
    if column.kind is columns.ColumnKind.INT:
        low = "" if column.low is None else str(column.low)
        high = "" if column.high is None else str(column.high)
        return f"int|{low}|{high}"
    return str(column.kind.value)


def columns_block_render() -> list[str]:
    """The lines between the markers, without the markers."""
    lines = [
        "# Generated from src\\camerasettings\\camerasettings_columns.py by scripts\\dev\\columns_block.py: the",
        "# column table as data. Regenerate it with --write; never edit it here.",
        "$colQuote = @{}",
        "$colKind = @{}",
        "$colRole = @{}",
        "$colWords = @{}",
    ]
    for column in columns.DEVICE_COLUMNS + columns.ANALYTICS_COLUMNS:
        if not column.name:
            continue
        if column.quote:
            lines.append(f"$colQuote[{_ps(column.name)}] = {_ps(column.quote)}")
        if column.kind is not columns.ColumnKind.TEXT:
            lines.append(f"$colKind[{_ps(column.name)}] = {_ps(_kind(column))}")
        if column.role is not columns.ColumnRole.APPLIED:
            lines.append(f"$colRole[{_ps(column.name)}] = {_ps(column.role.value)}")
    for name, words in (("CameraType", columns.CAMERA_TYPES), ("AnalyticsSceneMode", columns.SCENE_MODES),
                        ("VideoAnalyticsMode", columns.VIDEO_ANALYTICS_MODES)):
        pairs = "; ".join(f"{_ps(code)} = {_ps(word)}" for code, word in words.items())
        lines.append(f"$colWords[{_ps(name)}] = @{{ {pairs} }}")
    return lines


def _text(bat: Path) -> str:
    """Bytes, decoded: read_text would fold the CRLF the batch files must keep."""
    return bat.read_bytes().decode("ascii")


def _bats_with_block() -> list[Path]:
    return [bat for bat in sorted(ROOT.glob("*.bat")) if START in _text(bat)]


def _split(text: str) -> tuple[str, list[str], str]:
    """The text before the start marker line, the block lines, and the text from the end marker on."""
    lines = text.split("\r\n")
    start = lines.index(START)
    end = lines.index(END)
    return "\r\n".join(lines[: start + 1]) + "\r\n", lines[start + 1:end], "\r\n".join(lines[end:])


def columns_block_check() -> list[str]:
    """One line per root .bat whose block is not the generated one."""
    wanted = columns_block_render()
    return [f"{bat.name}: the COLS block is stale - run scripts\\dev\\columns_block.py --write"
            for bat in _bats_with_block() if _split(_text(bat))[1] != wanted]


def columns_block_write() -> list[str]:
    written = []
    for bat in _bats_with_block():
        head, current, tail = _split(_text(bat))
        if current != columns_block_render():
            bat.write_bytes((head + "\r\n".join(columns_block_render()) + "\r\n" + tail).encode("ascii"))
            written.append(bat.name)
    return written


def main(argv: list[str]) -> int:
    if argv == ["--check"]:
        problems = columns_block_check()
        for problem in problems:
            print("FAIL", problem)
        print("COLS block current in: " + ", ".join(b.name for b in _bats_with_block()) if not problems else "")
        return 1 if problems else 0
    if argv == ["--write"]:
        written = columns_block_write()
        print("rewritten: " + (", ".join(written) if written else "nothing - every copy was current"))
        return 0
    print("\n".join(columns_block_render()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
