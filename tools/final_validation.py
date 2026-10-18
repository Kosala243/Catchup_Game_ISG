"""Phase 8 technical release audit (no generated presentation content).

Checks Python 3.10 *syntax* on runtime files, documentation consistency,
release ZIP checksums, and a real short CLI game in an extracted ZIP.
Optional checks validate user-authored media filenames and metadata.
Manual assessment and Windows GUI/tournament checks remain essential.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

# When run as `python tools/final_validation.py`, sys.path contains tools/, not
# necessarily the repository root. Import sibling scripts explicitly.
try:
    from .build_release import create_release, verify_release
    from .check_environment import check
    from .windows_smoke import smoke
except ImportError:  # Direct execution: python tools/final_validation.py
    from build_release import create_release, verify_release
    from check_environment import check
    from windows_smoke import smoke


MANUAL_CHECKS = (
    "Run from a CLEAN extracted build on Windows 11 with Python 3.10.7",
    "Open both pygame modes; verify input, controls, final screen and focus",
    "Exercise tournament White and Black, undo, crash resume and the 600s whole-game budget",
    "If required, build and test a Windows native executable; .bat is not a native .exe",
    "Independently prepare/check video <=10 min, including 2-3 min demo, and slides PDF",
    "Resolve academic-integrity and repository-visibility requirements before submission",
)


def check_source_syntax(root: Path) -> list[str]:
    """Detect syntax invalid under Python 3.10 grammar; not runtime proof."""
    errors: list[str] = []
    paths = [root / "main.py", *sorted((root / "src").rglob("*.py"))]
    for path in paths:
        if not path.is_file():
            errors.append(f"Missing source: {path.relative_to(root)}")
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 10))
        except (SyntaxError, UnicodeError) as err:
            errors.append(f"Python 3.10 syntax error in {path.relative_to(root)}: {err}")
    return errors


def check_documentation(root: Path) -> list[str]:
    errors: list[str] = []
    for filename in ("README.md", "AI_USAGE.md"):
        path = root / filename
        if not path.is_file():
            errors.append(f"Missing documentation: {filename}")
            continue
        text = path.read_text(encoding="utf-8").lower()
        if "random-move stand-in" in text or "random-move placeholder" in text:
            errors.append(f"Outdated placeholder description in {filename}")
        if filename == "AI_USAGE.md":
            if not ("phase 2" in text and "phase 3" in text
                    and ("generative ai" in text or "genai" in text)):
                errors.append("AI_USAGE.md must disclose the AI assistance across phases 2 and 3")
    return errors


def validate_media(video: Path, slides: Path, *, ffprobe: str | None = None,
                   require_duration: bool = False) -> tuple[list[str], list[str]]:
    """Basic file signatures and MP4 duration; cannot assess slide/video quality."""
    errors: list[str] = []
    warnings: list[str] = []
    if not video.is_file():
        errors.append(f"Missing user-authored video: {video}")
    else:
        with video.open("rb") as handle:
            header = handle.read(16)
        if len(header) < 12 or header[4:8] != b"ftyp":
            errors.append(f"Not an MP4 with a valid ftyp header: {video}")
        if video.stat().st_size > 250 * 1024 * 1024:
            warnings.append("Video is larger than 250 MB; course requests compression, but sets no exact MB limit")
    if not slides.is_file():
        errors.append(f"Missing user-authored slides PDF: {slides}")
    else:
        with slides.open("rb") as handle:
            header = handle.read(8)
            handle.seek(max(0, slides.stat().st_size - 2048))
            tail = handle.read()
        if not header.startswith(b"%PDF-") or b"%%EOF" not in tail:
            errors.append(f"Slides PDF missing expected PDF signature/end marker: {slides}")
    if video.is_file() and not any("MP4" in error for error in errors):
        binary = ffprobe or shutil.which("ffprobe")
        if binary is None:
            note = "MP4 duration not checked: ffprobe unavailable; verify length manually"
            (errors if require_duration else warnings).append(note)
        else:
            try:
                run = subprocess.run(
                    [binary, "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
                    capture_output=True, text=True, timeout=15, check=False,
                )
                duration = float(run.stdout.strip()) if run.returncode == 0 else math.nan
                if not math.isfinite(duration) or duration <= 0:
                    errors.append("ffprobe could not determine a valid MP4 duration")
                elif duration > 600.0:
                    errors.append(f"Video exceeds the 10-minute limit ({duration:.1f} seconds)")
            except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                errors.append(f"Unable to inspect MP4 duration: {error}")
    return errors, warnings


def audit(root: Path, *, output: Path | None = None,
          game_budget: float = 1.5, strict_windows: bool = False,
          require_gui: bool = False, media_dir: Path | None = None,
          strict_duration: bool = False) -> dict:
    root = Path(root).resolve()
    output = (output or (root / "dist" / "Catchup_Windows_Source.zip")).resolve()
    report = {"status": "PASS", "automated_checks": {}, "errors": [],
              "warnings": [], "manual_checks_remaining": list(MANUAL_CHECKS),
              "source_root": str(root), "release_zip": str(output)}
    errs = report["errors"]
    errs.extend(check(root, require_windows=strict_windows,
                      require_python_310=strict_windows, gui=require_gui))
    report["automated_checks"]["environment"] = "PASS" if not errs else "FAIL"
    syntax_errors = check_source_syntax(root)
    errs.extend(syntax_errors)
    report["automated_checks"]["python_310_syntax"] = "PASS" if not syntax_errors else "FAIL"
    doc_errors = check_documentation(root)
    errs.extend(doc_errors)
    report["automated_checks"]["documentation"] = "PASS" if not doc_errors else "FAIL"
    if media_dir is not None:
        media_errors, media_warnings = validate_media(
            media_dir / "video.mp4", media_dir / "slides.pdf", require_duration=strict_duration
        )
        errs.extend(media_errors)
        report["warnings"].extend(media_warnings)
        report["automated_checks"]["media_metadata"] = "PASS" if not media_errors else "FAIL"
    try:
        archive, count = create_release(root, output)
        assert verify_release(archive) == count
        report["automated_checks"]["release_checksums"] = f"PASS ({count} files)"
        # Real integration run from a CLEAN extracted package, not from source tree.
        with tempfile.TemporaryDirectory(prefix="catchup_release_audit_") as tmp:
            with zipfile.ZipFile(archive) as z:
                z.extractall(tmp)
            result = smoke(Path(tmp) / "Catchup", budget_seconds=game_budget,
                           timeout_seconds=120)
        report["automated_checks"]["extracted_release_selfplay"] = (
            f"PASS ({result['turns']} turns; winner={result['winner']})")
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired,
            zipfile.BadZipFile, AssertionError) as error:
        errs.append(f"Release verification or extracted smoke failed: {error}")
        report["automated_checks"]["release_integration"] = "FAIL"
    if errs:
        report["status"] = "FAIL"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None, help="Where to save source ZIP")
    parser.add_argument("--budget-seconds", type=float, default=1.5,
                        help="Whole-game budget per AI during extracted-release smoke")
    parser.add_argument("--windows", action="store_true", help="Require Windows 11 and Python 3.10")
    parser.add_argument("--gui", action="store_true", help="Require Pygame availability")
    parser.add_argument("--media-dir", type=Path, help="Folder containing user-created video.mp4 and slides.pdf")
    parser.add_argument("--strict-duration", action="store_true", help="Fail if video duration cannot be checked")
    parser.add_argument("--report", type=Path, help="Write machine-readable JSON report")
    args = parser.parse_args()
    if not (0 < args.budget_seconds <= 600):
        parser.error("--budget-seconds must be greater than 0 and <=600")
    root = args.root.resolve()
    output = None if args.output is None else (args.output if args.output.is_absolute() else root / args.output)
    media = args.media_dir
    if media is not None and not media.is_absolute():
        media = root / media
    report = audit(root, output=output, game_budget=args.budget_seconds,
                   strict_windows=args.windows, require_gui=args.gui,
                   media_dir=media, strict_duration=args.strict_duration)
    print(json.dumps(report, indent=2))
    if args.report:
        dest = args.report if args.report.is_absolute() else root / args.report
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
