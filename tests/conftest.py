# Puts the one container under src/ on sys.path so tests import its modules by their own names
# (import camerasettings_csvfile), and keeps __pycache__ out of the tree. pytest loads it for
# everything under tests/, which is every test there is, so it need not sit at the root.
import os
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CODE = str(_PROJECT_ROOT / "src" / "camerasettings")
if _CODE not in sys.path:
    sys.path.insert(0, _CODE)


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    """Python compiles conftest.py before the flag above runs; wipe that one residue."""
    for cache in (_PROJECT_ROOT / "__pycache__", Path(__file__).parent / "__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)
