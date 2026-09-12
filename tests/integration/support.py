"""Shared test plumbing: the script under test, its embedded PowerShell blocks, a stand-in for
CCT-Batch, and loopback listeners that make a chosen 127.x address look like it has a web port.

CAMERA_SETTINGS_BAT points the tests at another copy of the script - how scripts/dev/mutate.py breaks
a gate without touching the real file.
"""
import datetime
import json
import os
import shutil
import socket
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BAT = Path(os.environ.get("CAMERA_SETTINGS_BAT", ROOT / "export.bat"))
IMPORT_BAT = Path(os.environ.get("CAMERA_SETTINGS_IMPORT_BAT", ROOT / "import.bat"))
CCT_EXE = Path(r"C:\Program Files (x86)\Motorola Solutions\Camera Configuration Tool\CCT-Batch.exe")
STUB = Path(__file__).with_name("stub_cct.py")

# The same one-liner the script uses to cut a block out of itself, so a test runs exactly what
# the technician's machine runs.
BLOCK_RUNNER = ("$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'{0}###';$i=$t.IndexOf($a)+$a.Length;"
                "$j=$t.IndexOf('###END'+'{0}###');Invoke-Expression $t.Substring($i,$j-$i)")

# Where CCT-Batch appends its console output, relative to LOCALAPPDATA.
CCT_LOG_DIR = Path("Motorola Solutions", "Camera Configuration Tool", "logs", "CCT Batch")

CCT_LINE = 'set "CCT=C:\\Program Files (x86)\\Motorola Solutions\\Camera Configuration Tool\\CCT-Batch.exe"'
ELEVATION_GATE = "net session >nul 2>&1\r\nif not errorlevel 1 goto elevated\r\n"


def today_log_name() -> str:
    return datetime.date.today().strftime("%Y-%m-%d") + "_batchconsole.log"


def run_block(name: str, env: dict, timeout: int = 120, script: Path | None = None) -> subprocess.CompletedProcess:
    full = {**os.environ, **env, "PSSELF": str(script or BAT)}
    return subprocess.run(["powershell", "-NoProfile", "-Command", BLOCK_RUNNER.format(name)],
                          env=full, capture_output=True, text=True, timeout=timeout)


def run_code(blocks: list[str], code: str, env: dict, script: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    """Load the named blocks out of the script, then run a line of PowerShell against their functions."""
    loader = "; ".join(BLOCK_RUNNER.format(name) for name in blocks)
    full = {**os.environ, **env, "PSSELF": str(script or IMPORT_BAT)}
    return subprocess.run(["powershell", "-NoProfile", "-Command", loader + "; " + code],
                          env=full, capture_output=True, text=True, timeout=timeout)


class Listener:
    """Accepts and immediately closes connections on one address and port."""

    def __init__(self, ip: str, port: int):
        self.ip, self.port = ip, port
        self.sock = socket.socket()

    def __enter__(self):
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.ip, self.port))
        self.sock.listen(200)
        threading.Thread(target=self._serve, daemon=True).start()
        return self

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            conn.close()

    def __exit__(self, *exc):
        self.sock.close()


def substitute_once(text: str, old: str, new: str) -> str:
    """A test-only edit to the script. Exactly one match, so drift in the real file is caught."""
    if text.count(old) != 1:
        raise AssertionError(f"expected exactly one occurrence of {old!r}, found {text.count(old)}")
    return text.replace(old, new)


def prepare_script(workdir: Path, cct_path: Path | None, script: Path | None = None, cct_calls: int = 1) -> Path:
    """Copy the script into workdir with the elevation gate removed (the tests cannot answer a UAC
    prompt) and, when a stand-in is given, pointed at it and invoked with call so a .bat returns.

    cct_calls is how many times the script invokes CCT - one for the export, two for the import,
    which exports and then imports. An exact count, so a call added or lost is caught here.
    """
    source = script or BAT
    text = source.read_bytes().decode("ascii")
    text = substitute_once(text, ELEVATION_GATE, "goto elevated\r\n")
    if cct_path is not None:
        text = substitute_once(text, CCT_LINE, f'set "CCT={cct_path}"')
        call = '"%CCT%" -a '
        if text.count(call) != cct_calls:
            raise AssertionError(f"expected {cct_calls} CCT calls in {source.name}, found {text.count(call)}")
        text = text.replace(call, 'call "%CCT%" -a ')
    target = workdir / source.name
    target.write_bytes(text.encode("ascii"))
    return target


def prepare_stub(workdir: Path, plan: dict) -> Path:
    """The stand-in CCT-Batch: a .bat that hands its arguments to stub_cct.py."""
    stub_dir = workdir / "stub"
    stub_dir.mkdir()
    shutil.copy(STUB, stub_dir / "stub_cct.py")
    (stub_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    wrapper = stub_dir / "CCT-Batch.bat"
    wrapper.write_bytes(b'@echo off\r\npython "%~dp0stub_cct.py" %*\r\nexit /b %ERRORLEVEL%\r\n')
    return wrapper


def run_script(script: Path, answers: list[str], env: dict, timeout: int,
               args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Drive the whole script with the form in its plain, redirected-input mode.

    The answers go in through a FILE, not a pipe. CMD's `set /p` reads a block from its input and
    seeks back to the end of the line it used; on a pipe it cannot seek, so everything after the
    first answer is lost and the second prompt sees end-of-input. The import script asks again
    after the form closes, so a pipe would test something the technician never does.
    """
    full = {**os.environ, **env}
    answer_file = script.parent / "answers.txt"
    answer_file.write_bytes(("\r\n".join(answers) + "\r\n").encode("cp1252"))
    with answer_file.open("rb") as stdin:
        return subprocess.run(["cmd", "/c", str(script), *(args or [])], stdin=stdin, env=full,
                              cwd=str(script.parent), capture_output=True, text=True, timeout=timeout,
                              encoding="cp1252", errors="replace")


def utf16_lines(path: Path) -> list[str]:
    raw = path.read_bytes()
    assert raw[:2] == b"\xff\xfe", f"{path.name} does not start with the UTF-16 byte-order mark"
    return raw[2:].decode("utf-16-le").splitlines()
