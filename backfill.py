"""Re-sorts files ALREADY sitting in the category folders.

The tray app only ever scans the Downloads root (non-recursive), so files sorted
under the old rules keep whatever category they landed in. This applies the
current config - name_rules included - to everything already filed.

    python backfill.py --dry-run   # show what would move
    python backfill.py             # move, logging every move to backfill_log.jsonl
    python backfill.py --undo      # put the last run's files back
"""
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from sorter import build_extension_map, build_name_matchers, category_for, dest_path

APP_DIR = Path(__file__).parent
LOG_PATH = APP_DIR / "backfill_log.jsonl"


def load():
    cfg = json.loads((APP_DIR / "config.json").read_text(encoding="utf-8"))
    cfg["watch_folder"] = os.path.expandvars(cfg["watch_folder"])
    return cfg


def plan(cfg):
    root = Path(cfg["watch_folder"])
    ext = build_extension_map(cfg["rules"])
    names = build_name_matchers(cfg.get("name_rules", []))
    categories = {r["category"] for r in cfg["rules"]}
    categories |= {r["category"] for r in cfg.get("name_rules", [])}
    skip = set(cfg.get("skip_names", []))

    moves = []
    for folder in sorted(categories):
        src_dir = root / folder
        if not src_dir.is_dir():
            continue
        for f in sorted(src_dir.iterdir()):
            if not f.is_file() or f.name in skip:
                continue
            target = category_for(f.name, ext, names)
            if target and target != folder:
                _, dest = dest_path(root, target, f.name)
                moves.append((f, dest, folder, target))
    return moves


def undo():
    if not LOG_PATH.exists():
        print("no backfill log to undo")
        return
    entries = [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line]
    if not entries:
        print("no backfill log to undo")
        return
    last_run = entries[-1]["run"]
    restored = 0
    for e in reversed([x for x in entries if x["run"] == last_run]):
        src, dst = Path(e["to"]), Path(e["from"])
        if not src.exists():
            print(f"  skip (gone) {src.name}")
            continue
        if dst.exists():
            # shutil.move would silently overwrite it on Windows - never lose a newer file.
            print(f"  skip (original path is occupied) {dst.name}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        restored += 1
    print(f"restored {restored} file(s) from run {last_run}")


def execute(moves, run_id, dry=False):
    """Perform (or, with dry=True, only print) the planned moves. Returns the
    log entries for the moves that actually happened."""
    done = []
    for src, dest, from_cat, to_cat in moves:
        print(f"  {from_cat:<11} -> {to_cat:<10} {src.name}")
        if dry:
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            done.append({"run": run_id, "from": str(src), "to": str(dest),
                         "from_category": from_cat, "to_category": to_cat})
        except OSError as err:
            print(f"    ! skipped: {err}")
    return done


def main():
    if "--undo" in sys.argv:
        return undo()

    cfg = load()
    moves = plan(cfg)
    dry = "--dry-run" in sys.argv

    if not moves:
        print("nothing to re-sort - every filed document already matches the rules")
        return

    run_id = datetime.now(timezone.utc).isoformat()
    done = execute(moves, run_id, dry=dry)

    if dry:
        print(f"\n[dry run] {len(moves)} file(s) would move")
        return

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        for entry in done:
            f.write(json.dumps(entry) + "\n")
    print(f"\nmoved {len(done)} file(s)  (undo: python backfill.py --undo)")


if __name__ == "__main__":
    main()
