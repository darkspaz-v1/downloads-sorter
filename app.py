import json
import logging
import msvcrt
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pystray

from icon import app_icon
from log_setup import setup_logging
from sorter import StabilityTracker, find_ready_to_sort

APP_DIR = Path(__file__).parent
CONFIG_PATH = APP_DIR / "config.json"
LOCK_PATH = APP_DIR / ".singleton.lock"
MOVE_LOG_PATH = APP_DIR / "move_log.jsonl"
MAX_LOG_ENTRIES = 500
_lock_file = None
log = logging.getLogger("downloads-sorter")

DEFAULT_CONFIG = {
    "watch_folder": "%USERPROFILE%\\Downloads",
    "poll_interval_seconds": 4,
    "stability_checks": 2,
    "ignored_extensions": [".crdownload", ".tmp", ".part", ".download", ".partial"],
    "skip_names": ["desktop.ini"],
    "rules": [],
}


def _acquire_single_instance_lock():
    """Best-effort single-instance guard via an exclusive OS file lock (stdlib
    msvcrt, Windows-only, no extra dependency)."""
    global _lock_file
    f = open(LOCK_PATH, "a+b")
    if f.tell() == 0:
        f.write(b"0")
        f.flush()
    f.seek(0)
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        return False
    _lock_file = f
    return True


def load_config():
    config = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except FileNotFoundError:
        pass
    config["watch_folder"] = os.path.expandvars(config["watch_folder"])
    return config


def log_move(src_name, category, dest):
    entry = {
        "time": datetime.now(timezone.utc).isoformat(),
        "file": src_name,
        "category": category,
        "dest": str(dest),
    }
    lines = []
    if MOVE_LOG_PATH.exists():
        try:
            lines = MOVE_LOG_PATH.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            # Unreadable log: start a fresh one rather than lose the move being logged.
            log.warning("could not read move log, starting a new one: %s", e)
            lines = []
    lines.append(json.dumps(entry))
    lines = lines[-MAX_LOG_ENTRIES:]
    MOVE_LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


class DownloadsSorterApp:
    def __init__(self):
        self.config = load_config()
        self.tracker = StabilityTracker(required_checks=self.config.get("stability_checks", 2))
        self._stop = threading.Event()
        self._paused = threading.Event()
        self.icon = None
        self.total_sorted = 0

    def poll_loop(self):
        while not self._stop.is_set():
            time.sleep(self.config["poll_interval_seconds"])
            if self._paused.is_set():
                continue
            try:
                ready = find_ready_to_sort(self.config["watch_folder"], self.config, self.tracker)
            except Exception:
                # The poller thread must survive anything a scan throws (odd filenames,
                # permissions, a folder vanishing); skip this cycle and try again.
                log.exception("scan of %s failed; retrying next poll", self.config["watch_folder"])
                continue
            for src, dest_dir, dest, category in ready:
                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dest))
                    self.tracker.forget(src)
                    log_move(src.name, category, dest)
                    self.total_sorted += 1
                except OSError as e:
                    # File may have been removed/renamed/opened elsewhere between the
                    # scan and the move - just skip it, it'll be re-evaluated next poll.
                    log.warning("could not move %s: %s", src.name, e)
                    continue
            if self.icon:
                self.icon.title = self._status_text()

    def _status_text(self):
        state = "paused" if self._paused.is_set() else "watching"
        return f"Downloads Sorter ({state}) - {self.total_sorted} sorted"

    def toggle_pause(self, icon=None, item=None):
        if self._paused.is_set():
            self._paused.clear()
        else:
            self._paused.set()
        if self.icon:
            self.icon.title = self._status_text()

    def is_paused(self, item=None):
        return self._paused.is_set()

    def open_watch_folder(self, icon=None, item=None):
        try:
            os.startfile(self.config["watch_folder"])
        except OSError as e:
            log.warning("could not open %s: %s", self.config["watch_folder"], e)

    def quit_app(self, icon=None, item=None):
        self._stop.set()
        if self.icon:
            self.icon.stop()

    def run(self):
        threading.Thread(target=self.poll_loop, daemon=True).start()

        menu = pystray.Menu(
            pystray.MenuItem("Open Downloads", self.open_watch_folder, default=True),
            pystray.MenuItem("Pause sorting", self.toggle_pause, checked=self.is_paused),
            pystray.MenuItem("Quit", self.quit_app),
        )
        self.icon = pystray.Icon("downloads-sorter", app_icon(), self._status_text(), menu)
        self.icon.run()


def main():
    if not _acquire_single_instance_lock():
        # Already running in the background - there's no window to "open", so
        # just do the one useful thing a relaunch could mean: show the folder
        # it's watching. Otherwise this would silently do nothing, which is
        # indistinguishable from being broken (e.g. when relaunched from the
        # Launcher).
        try:
            config = load_config()
            os.startfile(config["watch_folder"])
        except OSError as e:
            log.warning("could not open %s: %s", config["watch_folder"], e)
        return
    app = DownloadsSorterApp()
    app.run()


if __name__ == "__main__":
    setup_logging()
    try:
        main()
    except Exception:
        log.exception("fatal error")
        import traceback

        with open(APP_DIR / "app_error.log", "a", encoding="utf-8") as f:
            f.write(f"\n--- {time.ctime()} ---\n")
            f.write(traceback.format_exc())
        raise
