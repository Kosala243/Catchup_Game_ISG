"""Phase 8 audits: source syntax, disclosure, MP4/PDF metadata, optional exe builder."""
from pathlib import Path
import shutil
import sys

import pytest

from tools import final_validation as validator
from tools.build_native_windows import build_command, build


def test_syntax_check_real_project():
    project = Path(__file__).resolve().parents[1]
    assert validator.check_source_syntax(project) == []


def test_readme_and_ai_disclosure_current():
    project = Path(__file__).resolve().parents[1]
    assert validator.check_documentation(project) == []


def test_old_ai_usage_is_rejected(tmp_path):
    (tmp_path / 'README.md').write_text('Alpha-beta implemented.\n')
    (tmp_path / 'AI_USAGE.md').write_text('random-move placeholder\n')
    issues = validator.check_documentation(tmp_path)
    assert any('Outdated' in s for s in issues)


def test_missing_media_is_rejected(tmp_path):
    errors, warnings = validator.validate_media(tmp_path / 'video.mp4', tmp_path / 'slides.pdf')
    assert len(errors) == 2


def test_invalid_media_signatures_are_rejected(tmp_path):
    mp4, slides = tmp_path / 'video.mp4', tmp_path / 'slides.pdf'
    mp4.write_bytes(b'NOT A MOVIE')
    slides.write_bytes(b'NOT PDF')
    errors, _ = validator.validate_media(mp4, slides)
    assert len(errors) == 2


def test_media_duration_with_ffprobe(tmp_path, monkeypatch):
    video, slides = tmp_path / 'video.mp4', tmp_path / 'slides.pdf'
    video.write_bytes(b'\x00\x00\x00\x18ftypisom' + b'0' * 12)
    slides.write_bytes(b'%PDF-1.4\ncontents\n%%EOF\n')

    class Result:
        stdout = '599.9\n'
        returncode = 0

    monkeypatch.setattr(validator.subprocess, 'run', lambda *a, **k: Result())
    errors, warnings = validator.validate_media(video, slides, ffprobe='ffprobe')
    assert errors == [] and warnings == []
    Result.stdout = '600.01\n'
    errors, _ = validator.validate_media(video, slides, ffprobe='ffprobe')
    assert any('10-minute' in e for e in errors)


def test_no_duration_inspector_warns_or_fails(tmp_path, monkeypatch):
    video, slides = tmp_path / 'video.mp4', tmp_path / 'slides.pdf'
    video.write_bytes(b'\x00\x00\x00\x18ftypisom' + b'0' * 12)
    slides.write_bytes(b'%PDF-1.4\n%%EOF')
    monkeypatch.setattr(validator.shutil, 'which', lambda _: None)
    problems, warnings = validator.validate_media(video, slides)
    assert problems == [] and any('not checked' in w for w in warnings)
    problems, warnings = validator.validate_media(video, slides, require_duration=True)
    assert any('not checked' in e for e in problems)


def test_native_build_command_has_correct_packaging_and_console(tmp_path):
    cmd = build_command(tmp_path, executable='py')
    assert cmd[:3] == ['py', '-m', 'PyInstaller']
    assert '--onedir' in cmd and '--console' in cmd
    assert str(tmp_path / 'main.py') == cmd[-1]
    assert '--distpath' in cmd and '--workpath' in cmd


def test_native_build_rejected_outside_windows(tmp_path):
    if sys.platform != 'win32':
        with pytest.raises(OSError, match='Windows'):
            build(tmp_path)


def test_media_size_is_warning_not_undocumented_cap(tmp_path, monkeypatch):
    # Regression for the course wording: compression recommended, not a fixed MB restriction.
    video, slides = tmp_path / 'video.mp4', tmp_path / 'slides.pdf'
    video.write_bytes(b'\x00\x00\x00\x18ftypisom')
    slides.write_bytes(b'%PDF-1.4\n%%EOF')
    monkeypatch.setattr(validator.shutil, 'which', lambda x: None)
    errors, warnings = validator.validate_media(video, slides)
    assert errors == []
    assert any('duration' in w for w in warnings)


def test_release_contains_phase8_auditing_tools(tmp_path):
    from tools.build_release import create_release, verify_release
    import zipfile
    project = Path(__file__).resolve().parents[1]
    target = tmp_path / "release.zip"
    create_release(project, target)
    assert verify_release(target) > 30
    with zipfile.ZipFile(target) as zipped:
        names = set(zipped.namelist())
    assert "Catchup/tools/final_validation.py" in names
    assert "Catchup/tools/build_release.py" in names
    assert "Catchup/tools/build_native_windows.py" in names
    assert "Catchup/PHASE8_README.md" in names
