import json

import pytest

import backfill
from sorter import build_extension_map, build_name_matchers, category_for


@pytest.fixture
def cfg(tmp_path):
    config = json.loads((backfill.APP_DIR / "config.json").read_text(encoding="utf-8"))
    config["watch_folder"] = str(tmp_path)
    return config


@pytest.fixture
def log(tmp_path, monkeypatch):
    path = tmp_path / "_backfill_log.jsonl"
    monkeypatch.setattr(backfill, "LOG_PATH", path)
    return path


def filed(root, folder, name, text="data"):
    d = root / folder
    d.mkdir(exist_ok=True)
    (d / name).write_text(text)
    return d / name


def test_plan_moves_only_misfiled_files(tmp_path, cfg):
    filed(tmp_path, "Documents", "CHEM135_HW3.pdf")  # should be School
    filed(tmp_path, "Documents", "plain.pdf")  # correctly filed
    filed(tmp_path, "Images", "cat.png")  # correctly filed
    moves = backfill.plan(cfg)
    assert [(m[0].name, m[2], m[3]) for m in moves] == [("CHEM135_HW3.pdf", "Documents", "School")]
    assert moves[0][1] == tmp_path / "School" / "CHEM135_HW3.pdf"


def test_plan_skips_missing_category_folders_and_skip_names(tmp_path, cfg):
    filed(tmp_path, "Documents", "desktop.ini")
    assert backfill.plan(cfg) == []


def test_dry_run_moves_nothing(tmp_path, cfg):
    src = filed(tmp_path, "Documents", "syllabus.pdf")
    moves = backfill.plan(cfg)
    assert backfill.execute(moves, "run1", dry=True) == []
    assert src.exists()


def test_execute_then_undo_restores_original_layout(tmp_path, cfg, log):
    a = filed(tmp_path, "Documents", "syllabus.pdf", "A")
    b = filed(tmp_path, "Documents", "2024 tax return.pdf", "B")
    done = backfill.execute(backfill.plan(cfg), "run1")
    assert len(done) == 2
    assert not a.exists() and not b.exists()
    assert (tmp_path / "School" / "syllabus.pdf").read_text() == "A"
    assert (tmp_path / "Important" / "2024 tax return.pdf").read_text() == "B"

    log.write_text("".join(json.dumps(e) + "\n" for e in done), encoding="utf-8")
    backfill.undo()
    assert a.read_text() == "A" and b.read_text() == "B"
    assert not (tmp_path / "School" / "syllabus.pdf").exists()


def test_undo_only_reverts_the_last_run(tmp_path, log):
    old_src, new_src = tmp_path / "old_from.txt", tmp_path / "new_from.txt"
    old_dst, new_dst = tmp_path / "old_to.txt", tmp_path / "new_to.txt"
    old_dst.write_text("old")
    new_dst.write_text("new")
    entries = [
        {"run": "r1", "from": str(old_src), "to": str(old_dst)},
        {"run": "r2", "from": str(new_src), "to": str(new_dst)},
    ]
    log.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    backfill.undo()
    assert new_src.exists() and not new_dst.exists()
    assert old_dst.exists() and not old_src.exists()


def test_undo_skips_files_that_are_gone(tmp_path, log, capsys):
    entry = {"run": "r1", "from": str(tmp_path / "a.txt"), "to": str(tmp_path / "gone.txt")}
    log.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    backfill.undo()
    assert "skip (gone)" in capsys.readouterr().out


def test_undo_without_a_log_is_a_noop(log, capsys):
    backfill.undo()
    assert "no backfill log" in capsys.readouterr().out


@pytest.mark.xfail(strict=True, reason="bug: undo overwrites a file that reappeared at the original path")
def test_undo_does_not_overwrite_a_file_that_reappeared_at_the_original_path(tmp_path, log):
    # A new file with the same name was created where the sorted file used to be.
    original = tmp_path / "Documents" / "syllabus.pdf"
    moved = tmp_path / "School" / "syllabus.pdf"
    moved.parent.mkdir()
    original.parent.mkdir()
    moved.write_text("sorted copy")
    original.write_text("new download")
    entry = {"run": "r1", "from": str(original), "to": str(moved)}
    log.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    backfill.undo()
    assert original.read_text() == "new download"


def test_backfill_uses_same_rules_as_the_live_sorter(cfg):
    ext = build_extension_map(cfg["rules"])
    names = build_name_matchers(cfg["name_rules"])
    assert category_for("syllabus.pdf", ext, names) == "School"
