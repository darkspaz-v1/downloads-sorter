import json

import app


def test_log_move_appends_and_caps_at_max_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "MOVE_LOG_PATH", tmp_path / "move_log.jsonl")
    monkeypatch.setattr(app, "MAX_LOG_ENTRIES", 3)
    for i in range(5):
        app.log_move(f"f{i}.pdf", "Documents", tmp_path / "Documents" / f"f{i}.pdf")
    lines = (tmp_path / "move_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["file"] for line in lines] == ["f2.pdf", "f3.pdf", "f4.pdf"]
    assert json.loads(lines[0])["category"] == "Documents"


def test_load_config_expands_env_vars_in_watch_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cfg = app.load_config()
    assert cfg["watch_folder"] == str(tmp_path / "Downloads")
