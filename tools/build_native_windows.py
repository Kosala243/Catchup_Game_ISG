"""Optional native Windows executable build, run on Windows 11 only.

PyInstaller is a DEVELOPMENT dependency, not an assessment-machine dependency.
The *whole* onedir folder is required. The source ZIP is a separate artifact.
This does not certify the built executable; manually test it on Windows 11.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def build_command(root: Path, executable: str = sys.executable) -> list[str]:
    """Build a console executable so tournament input/output remains visible."""
    root = Path(root).resolve()
    return [
        executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--console", "--name", "Catchup",
        "--distpath", str(root / "dist" / "windows_exe"),
        "--workpath", str(root / "build" / "pyinstaller"),
        "--specpath", str(root / "build" / "pyinstaller"),
        "--hidden-import=pygame", str(root / "main.py"),
    ]


def build(root: Path) -> Path:
    if sys.platform != "win32":
        raise OSError("Windows executables must be built on Windows; PyInstaller cannot cross-compile from macOS/Linux")
    root = Path(root).resolve()
    if not (root / "main.py").is_file():
        raise FileNotFoundError("Missing main.py: build from the repository root")
    check = subprocess.run(
        [sys.executable, "-c", "import PyInstaller, pygame"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if check.returncode:
        raise RuntimeError("On your Windows DEVELOPMENT machine install PyInstaller and pygame: "
                           "python -m pip install pyinstaller pygame\n" + check.stderr)
    subprocess.run(build_command(root), cwd=root, check=True)
    exe = root / "dist" / "windows_exe" / "Catchup" / "Catchup.exe"
    if not exe.is_file():
        raise FileNotFoundError(f"PyInstaller reported success but {exe} was not created")
    return exe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        exe = build(args.root)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"Built: {exe}")
    print("Keep and transfer the ENTIRE dist/windows_exe/Catchup folder; test the executable on Windows 11.")
    print("Build source ZIP separately: python tools/build_release.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
