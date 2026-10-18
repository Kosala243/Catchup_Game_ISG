"""Dependency and operating-system preflight for a Catchup source release.

Uses only the Python standard library, so it runs even when pygame is missing.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import platform
import sys


def windows_11_or_later() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return sys.getwindowsversion().build >= 22000
    except AttributeError:
        return False


def check(root: Path, require_windows: bool = False, require_python_310: bool = False,
          gui: bool = False) -> list[str]:
    errors: list[str] = []
    if sys.version_info < (3, 10):
        errors.append("Catchup uses Python 3.10+ syntax; upgrade Python")
    if require_python_310 and sys.version_info[:2] != (3, 10):
        errors.append("The assessment environment requires Python 3.10.x")
    if require_windows and not windows_11_or_later():
        errors.append("This check requires Windows 11 or newer (build >= 22000)")
    if not (root / "main.py").is_file() or not (root / "src/engine/search.py").is_file():
        errors.append("Run from a complete Catchup release folder")
    if gui and importlib.util.find_spec("pygame") is None:
        errors.append("Pygame is missing (required for the graphical modes)")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gui", action="store_true", help="Require pygame to be importable")
    parser.add_argument("--require-windows", action="store_true", help="Require Windows 11+")
    parser.add_argument("--require-python-310", action="store_true", help="Require Python 3.10.x")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(f"Python: {platform.python_version()} at {sys.executable}")
    print(f"Platform: {platform.platform()}")
    print(f"Pygame available: {importlib.util.find_spec('pygame') is not None}")
    errors = check(root, args.require_windows, args.require_python_310, args.gui)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: Environment preflight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
