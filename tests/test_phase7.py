"""Release packaging, environment and smoke-result regression tests."""
from pathlib import Path
import shutil
import sys
import zipfile

import pytest

from tools.build_release import collect_files, create_release, verify_release, REQUIRED_FILES
from tools.check_environment import check
from tools.windows_smoke import validate_result


@pytest.fixture
def tiny_project(tmp_path):
    root = tmp_path / "repo"
    for filename in REQUIRED_FILES:
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {filename}\n", encoding="utf-8")
    (root / "src/engine/extra.py").write_text("pass\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests/dont_include.py").write_text("pass\n", encoding="utf-8")
    (root / "saves").mkdir()
    (root / "saves/current_game.json").write_text("{}", encoding="utf-8")
    return root


def test_release_contains_required_runtime_and_excludes_user_data(tiny_project, tmp_path):
    output = tmp_path / "output.zip"
    result, count = create_release(tiny_project, output)
    assert result == output.resolve()
    assert count == len(collect_files(tiny_project))
    assert verify_release(output) == count
    with zipfile.ZipFile(output) as z:
        paths = set(z.namelist())
        assert "Catchup/run.bat" in paths
        assert "Catchup/src/engine/extra.py" in paths
        assert "Catchup/SHA256SUMS.txt" in paths
        assert not any("saves/" in p or "tests/" in p for p in paths)


def test_missing_critical_file_rejected(tiny_project, tmp_path):
    (tiny_project / "src/engine/search.py").unlink()
    with pytest.raises(FileNotFoundError):
        create_release(tiny_project, tmp_path / "bad.zip")


def test_tampering_with_zip_is_detected(tiny_project, tmp_path):
    good = tmp_path / "good.zip"
    bad = tmp_path / "bad.zip"
    create_release(tiny_project, good)
    with zipfile.ZipFile(good) as source, zipfile.ZipFile(bad, "w") as dest:
        for member in source.namelist():
            data = source.read(member)
            if member == "Catchup/main.py":
                data = b"tampered contents\n"
            dest.writestr(member, data)
    with pytest.raises(ValueError, match="Checksum mismatch"):
        verify_release(bad)


def test_unsafe_or_unlisted_files_excluded(tiny_project):
    (tiny_project / "experiments").mkdir()
    (tiny_project / "experiments/results.csv").write_text("private data")
    (tiny_project / "src/game/test_notes.txt").parent.mkdir(parents=True, exist_ok=True)
    (tiny_project / "src/game/test_notes.txt").write_text("private data")
    rel = {p.relative_to(tiny_project).as_posix() for p in collect_files(tiny_project)}
    assert "experiments/results.csv" not in rel
    assert "src/game/test_notes.txt" not in rel


def test_environment_headless_preflight(tiny_project):
    assert check(tiny_project) == []
    if sys.platform != "win32":
        assert any("Windows" in e for e in check(tiny_project, require_windows=True))


def test_environment_missing_project(tmp_path):
    assert any("complete Catchup" in e for e in check(tmp_path))


def test_result_parser_accepts_finished_game():
    output = "{'winner': 'W', 'final_scores': {'W': 30, 'B': 19}, 'turns': 26, 'white_time_left': 596.0, 'black_time_left': 597.0}\n"
    result = validate_result(output)
    assert result["winner"] == "W" and result["turns"] == 26


@pytest.mark.parametrize("output", [
    "unexpected output", "{'winner': 'X', 'final_scores': {'W': 1, 'B': 1}, 'turns': 2, 'white_time_left': 4, 'black_time_left': 3}",
    "{'winner': 'W', 'final_scores': {'W': 1}, 'turns': 2, 'white_time_left': 4, 'black_time_left': 3}",
])
def test_result_parser_rejects_invalid_output(output):
    with pytest.raises(ValueError):
        validate_result(output)
