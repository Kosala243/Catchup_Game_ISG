"""Build and verify a portable, source-based Windows release ZIP.

Requires only Python's standard library. The generated archive contains the
runtime program plus a Windows .bat launcher, not a native Windows .exe.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

PACKAGE_NAME = "Catchup"
REQUIRED_FILES = (
    "main.py", "run.bat", "requirements.txt", "README.md", "AI_USAGE.md",
    "src/board/board.py", "src/game/state.py", "src/engine/search.py",
    "src/modes/tournament_mode.py", "src/modes/self_play.py",
    "tools/check_environment.py", "tools/windows_smoke.py",
)
OPTIONAL_FILES = ("PHASE7_README.md", "docs/architecture.md")
MANIFEST = "SHA256SUMS.txt"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collect_files(root: Path) -> list[Path]:
    """Whitelist source and runtime resources; never include saves or outputs."""
    root = Path(root).resolve()
    missing = [p for p in REQUIRED_FILES if not (root / p).is_file()]
    if missing:
        raise FileNotFoundError("Missing required release files: " + ", ".join(missing))
    filenames = set(REQUIRED_FILES)
    filenames.update(p for p in OPTIONAL_FILES if (root / p).is_file())
    filenames.update(
        p.relative_to(root).as_posix() for p in (root / "src").rglob("*.py")
        if p.is_file() and not p.is_symlink()
    )
    # Explicitly exclude tests, experiments, .venv, saves, videos, datasets,
    # generated PNG/CSV reports and platform-specific bytecode.
    files = [root / p for p in sorted(filenames)]
    for path in files:
        if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
            raise ValueError(f"Unsafe or unavailable release source: {path}")
    return files


def create_release(root: Path, output: Path) -> tuple[Path, int]:
    root = Path(root).resolve()
    output = Path(output).resolve()
    files = collect_files(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.is_dir():
        raise ValueError("Archive output must be a file")
    lines = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for file in files:
            relative = file.relative_to(root).as_posix()
            data = file.read_bytes()
            name = f"{PACKAGE_NAME}/{relative}"
            archive.writestr(name, data)
            lines.append(f"{sha256(data)}  {relative}")
        archive.writestr(
            f"{PACKAGE_NAME}/{MANIFEST}", ("\n".join(lines) + "\n").encode("utf-8")
        )
    verify_release(output)
    return output, len(files)


def verify_release(archive_path: Path) -> int:
    """Verify names, manifest checksums and required runtime paths."""
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        manifest_name = f"{PACKAGE_NAME}/{MANIFEST}"
        if len(names) != len(set(names)) or manifest_name not in names:
            raise ValueError("Missing checksum manifest or duplicated archive names")
        expected = {}
        for line in archive.read(manifest_name).decode("utf-8").splitlines():
            digest, sep, path = line.partition("  ")
            if not sep or len(digest) != 64 or not path or path in expected:
                raise ValueError("Malformed checksum manifest")
            expected[path] = digest
        actual_paths = set()
        for item in archive.infolist():
            name = item.filename
            segments = PurePosixPath(name).parts
            if (not name.startswith(f"{PACKAGE_NAME}/") or ".." in segments
                    or item.is_dir()):
                raise ValueError(f"Unsafe archive path: {name}")
            if name == manifest_name:
                continue
            relative = name[len(PACKAGE_NAME) + 1:]
            actual_paths.add(relative)
            if sha256(archive.read(item)) != expected.get(relative):
                raise ValueError(f"Checksum mismatch or missing entry: {relative}")
        if actual_paths != set(expected):
            raise ValueError("Manifest/file list does not match archive")
        if not set(REQUIRED_FILES).issubset(actual_paths):
            raise ValueError("A mandatory runtime file is missing")
        if any(p.startswith(("saves/", "tests/", "experiments/", "video/"))
               for p in actual_paths):
            raise ValueError("Release unexpectedly includes private or development data")
    return len(actual_paths)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Repository root (default: parent of tools/)")
    parser.add_argument("--output", type=Path,
                        default=Path("dist/Catchup_Windows_Source.zip"),
                        help="ZIP output path relative to repo root")
    parser.add_argument("--verify", type=Path,
                        help="Only verify an already built release ZIP")
    args = parser.parse_args()
    try:
        if args.verify:
            count = verify_release(args.verify)
            print(f"Verified ZIP: {args.verify} ({count} files)")
        else:
            output = args.output if args.output.is_absolute() else args.root / args.output
            result, count = create_release(args.root, output)
            print(f"Built and verified ZIP: {result} ({count} source/runtime files)")
    except (OSError, ValueError, zipfile.BadZipFile, UnicodeError) as error:
        print(f"Release check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
