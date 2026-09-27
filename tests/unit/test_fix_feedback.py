"""ROOK-039d: the Surgeon's feedback from earlier rounds is the same on every run (it is part of the next
prompt, so of its recording key): run-specific paths, keys and times are masked; the reasons stay."""

from pathlib import Path

from rook.agents.fix import FixRound, _feedback
from rook.agents.recorder import Recorder, RecordingMissing


def _rounds(workspace: Path, recordings: Path, key: str) -> list[FixRound]:
    try:
        Recorder(recordings).load(key)
        raise AssertionError("the recording should be missing")
    except RecordingMissing as exc:
        missing = f"the Surgeon gave no valid answer: {exc}"
    return [
        FixRound(1, "failed", missing, [], []),
        FixRound(2, "rejected", f"the fix breaks {workspace}/app.py:12 at 10:41:07; see /home/alice/x.log", ["app.py"],
                 []),
        FixRound(3, "guard", "changes outside the allowed files were reverted: tests/test_app.py", [], ["x"]),
    ]


def test_feedback_is_identical_across_runs_and_machines(tmp_path: Path) -> None:
    first = _feedback(_rounds(tmp_path / "ws1", tmp_path / "rec-a", "a" * 64), tmp_path / "ws1")
    second = _feedback(_rounds(Path("/home/rook/w/r_2"), Path("/home/rook/.rook/recordings"), "b" * 64),
                       Path("/home/rook/w/r_2"))
    assert first == second
    for volatile in (str(tmp_path), "/home/", "a" * 64, "10:41:07", "rec-a"):
        assert volatile not in first
    assert "Round 1: failed. the Surgeon gave no valid answer: no recording for this call" in first
    assert "Round 2: rejected. the fix breaks /workspace/app.py:12 at <time>; see <path>" in first
    assert "Files you changed: app.py" in first
    assert "Round 3: guard. changes outside the allowed files were reverted: tests/test_app.py" in first


def test_first_round_has_no_feedback(tmp_path: Path) -> None:
    assert _feedback([], tmp_path) == ""
