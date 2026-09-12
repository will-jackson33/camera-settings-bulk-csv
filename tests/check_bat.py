"""Static checks for the batch scripts. Run: python tests/check_bat.py

Every rule here is a defect class actually hit while building the export script, not a style
preference. A failure names the file, line and rule. Exit 0 clean, 1 otherwise.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Variables holding free text or paths. Expanded inside a parenthesised block, the ")" in a value
# like "Program Files (x86)" or "Example Club (Stage 2)" closes the block early - CMD dies on
# the rest of the line. Found live, twice.
FREE_TEXT = ("CCT", "SITE", "OUTDIR", "STAGE", "CSV", "LOG", "ZIP", "NAME", "BASENAME", "VERDICT",
             "STARTIP", "ENDIP", "IPRANGE", "DEFEND", "PSSRC", "PSZIP", "PSCSV", "CAMUSER",
             "SUBSTART", "SUBEND", "SUBRANGE", "SUBCSV", "PSOUT", "PSRPT", "IMPORTCSV", "PSDROP", "PHASE",
             "PSREADABLE", "PSANALYTICS", "ROLLBACK", "BACKUP", "DROPPATH")
FREE_TEXT_PATTERN = re.compile("%(" + "|".join(FREE_TEXT) + ")%")


def _code_lines(lines: list[str]) -> list[tuple[int, str]]:
    return [(i, ln.strip()) for i, ln in enumerate(lines, 1) if not ln.strip().lower().startswith("rem")]


def _labels(bat: Path, lines: list[str]) -> list[str]:
    labels = {ln.strip()[1:].split()[0].lower()
              for ln in lines if ln.strip().startswith(":") and not ln.strip().startswith("::")}
    problems = []
    for i, ln in enumerate(lines, 1):
        m = re.search(r"\bgoto\s+:?(\w+)", ln, re.I)
        if m and m.group(1).lower() not in labels and m.group(1).lower() != "eof":
            problems.append(f"{bat.name}:{i}: goto {m.group(1)} has no matching label")
    return problems


def _delayed_expansion(bat: Path, text: str) -> list[str]:
    # A password containing "!" is silently mangled under delayed expansion, and a mangled password
    # reads on screen as an offline camera.
    return [f"{bat.name}: enables delayed expansion"] if re.search(r"enabledelayedexpansion", text, re.I) else []


def _free_text_in_parentheses(bat: Path, lines: list[str]) -> list[str]:
    return [f"{bat.name}:{i}: free-text variable inside a parenthesised line"
            for i, s in _code_lines(lines) if "(" in s and FREE_TEXT_PATTERN.search(s)]


def _bounded_prompts(bat: Path, text: str) -> list[str]:
    # set /p returns instantly with no console attached; an unbounded ask-again loop spins forever
    # and fills the disk with prompt text. Every prompt loop must carry a retry bound.
    prompts = len(re.findall(r'^\s*set /p ', text, re.M))
    bounds = len(re.findall(r"GEQ \d+ goto ", text))
    return [f"{bat.name}: {prompts} prompts but no bounded retry loop"] if prompts and not bounds else []


def _no_find(bat: Path, lines: list[str]) -> list[str]:
    # Unix find shadows Windows find.exe on machines with Git Bash on the PATH, ignores /c, and
    # walks the whole drive. There is no safe spelling; do not call find at all.
    return [f"{bat.name}:{i}: calls find - shadowed by Unix find on tech laptops"
            for i, s in _code_lines(lines) if re.search(r"(^|[|&(\s'`])find(\.exe)?\s", s, re.I)]


def _mode_con(bat: Path, lines: list[str]) -> list[str]:
    # `mode con` reads standard input when it is not a console, so a width probe in a script whose
    # input is redirected eats the answers queued behind it. Always run it with <nul.
    return [f"{bat.name}:{i}: runs mode con without <nul - it would eat redirected input"
            for i, s in _code_lines(lines) if re.search(r"\bmode con\b", s, re.I) and "<nul" not in s.replace("^", "")]


def _block_markers(bat: Path, lines: list[str], text: str) -> list[str]:
    # Each embedded PowerShell block is cut out of this file by a marker pair. A marker that is
    # missing or doubled makes IndexOf answer -1 and Invoke-Expression runs whatever text lies
    # between; the CMD call sites split their marker strings so the search cannot find itself,
    # which is why this check reassembles them.
    problems = []
    starts = re.findall(r"^###PS(\w+)###\s*$", text, re.M)
    ends = re.findall(r"^###END(\w+)###\s*$", text, re.M)
    for name in sorted(set(starts) | set(ends)):
        if starts.count(name) != 1 or ends.count(name) != 1:
            problems.append(f"{bat.name}: block {name} needs exactly one ###PS{name}### and one ###END{name}###")
    for i, ln in enumerate(lines, 1):
        opened = re.findall(r"'###PS'\+'(\w+)###'", ln)
        closed = re.findall(r"'###END'\+'(\w+)###'", ln)
        for name in opened:
            if name not in starts:
                problems.append(f"{bat.name}:{i}: runs block {name}, which is not in the file")
        if opened != closed:
            problems.append(f"{bat.name}:{i}: block start and end markers on this line do not match")
    return problems


def check(bat: Path) -> list[str]:
    lines = bat.read_text(encoding="utf-8", errors="replace").splitlines()
    text = "\n".join(lines)
    return (_labels(bat, lines) + _delayed_expansion(bat, text) + _free_text_in_parentheses(bat, lines)
            + _bounded_prompts(bat, text) + _no_find(bat, lines) + _mode_con(bat, lines)
            + _block_markers(bat, lines, text))


# Blocks that exist in more than one script under one name are one block: the settings-file
# reader and the column table. Two copies that drift read the same file two ways.
SHARED_BLOCKS = ("CSV", "COLS")


def _shared_blocks(bats: list[Path]) -> list[str]:
    seen: dict[str, tuple[str, str]] = {}
    problems = []
    for bat in bats:
        text = bat.read_text(encoding="utf-8", errors="replace")
        for name, body in re.findall(r"^###PS(\w+)###\r?\n(.*?)^###END\1###", text, re.M | re.S):
            if name not in SHARED_BLOCKS:
                continue
            if name in seen and seen[name][1] != body:
                problems.append(f"block {name} differs between {seen[name][0]} and {bat.name} - one block, one text")
            seen.setdefault(name, (bat.name, body))
    return problems


def _version(bats: list[Path]) -> list[str]:
    # One version, stamped in every script's VERSION= line and in the Python entry point.
    # A technician holding an emailed folder reads it off the banner; two copies that disagree
    # make that reading a lie.
    problems = []
    found: dict[str, str] = {}
    for bat in bats:
        stamps = re.findall(r'^set "VERSION=(\d+\.\d+\.\d+)"\s*$', bat.read_text(encoding="utf-8", errors="replace"), re.M)
        if len(stamps) != 1:
            problems.append(f"{bat.name}: needs exactly one set \"VERSION=x.y.z\" line, found {len(stamps)}")
        else:
            found[bat.name] = stamps[0]
    entry = ROOT / "src" / "camerasettings" / "camerasettings_main.py"
    python = re.findall(r'^__version__ = "(\d+\.\d+\.\d+)"$', entry.read_text(encoding="utf-8"), re.M)
    if len(python) != 1:
        problems.append(f"{entry.name}: needs exactly one __version__ line, found {len(python)}")
    else:
        found[entry.name] = python[0]
    if len(set(found.values())) > 1:
        problems.append("the version differs: " + ", ".join(f"{name} {version}" for name, version in sorted(found.items())))
    return problems


def main() -> int:
    bats = sorted(ROOT.glob("*.bat"))
    if not bats:
        print("no .bat files found at project root")
        return 1
    failures: list[str] = _shared_blocks(bats) + _version(bats)
    for bat in bats:
        failures += check(bat)
    for f in failures:
        print("FAIL", f)
    print(("clean: " if not failures else "checked: ") + ", ".join(b.name for b in bats))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
