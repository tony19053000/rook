"""Every committed Bob recording (baked into the server image too) is free of local paths and user names."""

from pathlib import Path

RECORDINGS = Path(__file__).parents[1] / "fixtures" / "recordings"


def test_no_recording_holds_a_local_path() -> None:
    files = sorted(p for p in RECORDINGS.rglob("*") if p.is_file())
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        for marker in ("pytest-of-", "/home/", "/tmp/"):
            assert marker not in text, f"{path.relative_to(RECORDINGS)} holds {marker!r}"
