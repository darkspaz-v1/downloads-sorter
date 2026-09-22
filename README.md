# Downloads Sorter

[![CI](https://github.com/darkspaz-v1/downloads-sorter/actions/workflows/ci.yml/badge.svg)](https://github.com/darkspaz-v1/downloads-sorter/actions/workflows/ci.yml)

Keeps the Downloads folder from turning into a junk drawer, without any interaction.

### Example (illustrative — not real files)

A Downloads folder before the sorter runs:

```
Downloads/
├── fake-report.pdf
├── fake-photo.jpg
├── fake-installer.exe
├── fake-archive.zip
├── fake-mix.mp3
└── fake-demo.mp4
```

The same folder after sorting:

```
Downloads/
├── Documents/
│   └── fake-report.pdf
├── Images/
│   └── fake-photo.jpg
├── Installers/
│   └── fake-installer.exe
├── Archives/
│   └── fake-archive.zip
├── Audio/
│   └── fake-mix.mp3
├── Videos/
│   └── fake-demo.mp4
└── move_log.jsonl
```

The filenames above are made up for illustration — the tool never touches, reads, or uploads the
contents of your real files, it only moves them by extension (and optionally by filename keyword;
see `config.json`).

## How it works

- Tray-only. There is no main window by design.
- Watches the real Downloads folder and files each new item into a type subfolder — Images,
  Documents, Archives, Installers, Videos, Audio.
- **Waits for the file size to stop changing before moving anything.** This is the whole trick: a
  browser writes a partial file immediately, so acting on file creation moves half-downloaded files
  and breaks the download. A file is only eligible once its size is stable across polls.
- Every move is appended to `move_log.jsonl`, so a surprise is traceable rather than mysterious.
- `backfill.py` applies the same rules to files that predate the watcher, for a one-off cleanup.

## Notes from building it

- Because there is no window, relaunching it (from a launcher, say) **opens the watched Downloads
  folder** instead of doing nothing — the only useful thing a relaunch could mean for a tray app.
- `move_log.jsonl` and `backfill_log.jsonl` contain real filenames and are gitignored.

**Stack:** Python, `pystray`, Pillow.

## Part of a suite

One of seven small Windows tray utilities built as separate, self-contained apps: each has its own
folder, its own virtualenv and its own `run.bat`, with no shared runtime. They are deliberately not a
framework — the only thing they share is a set of conventions.

| Convention | Why |
|---|---|
| Single-instance guard via a `.singleton.lock` file | An earlier `.instance.lock` design could get stuck after a force-kill and leave the app permanently unlaunchable |
| Relaunch brings the existing window forward | Previously a second launch silently did nothing, which was indistinguishable from the app being broken |
| Config lives in `config.json`, read at startup | Edit it, then fully exit the tray icon and relaunch — a running process never re-reads it |
| Tray icon generated in code (`icon.py`) | No binary asset to keep in sync |

## Quick start

```
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
run.bat
```

`run.bat` launches the app from `venv\` with no console window. Windows only - these use Win32 APIs and a
system tray.

## Tests

```
venv\Scripts\python -m pip install -r requirements-dev.txt
venv\Scripts\python -m pytest
venv\Scripts\python -m ruff check .
```

The tests cover the pure logic (type-folder mapping, whole-word School/Important rules, semester and course patterns, stable-file detection, backfill and its undo) against temporary folders. They never start the tray icon or touch your real Downloads folder.

## Known limitations

- **Windows only.** The tray icon, single-instance lock and folder watching all use Win32 APIs;
  there's no macOS/Linux support.
- **Waits for a file's size to stop changing before moving it.** A browser writes a partial file the
  moment a download starts, so moving on creation would relocate (and for some browsers, break) a
  half-downloaded file. The sorter only acts once a file's size is stable across polls.
- **`backfill.py --undo` only reverses the most recent backfill run.** There's no multi-run undo
  history — running `--undo` after several backfills only rolls back the last one.

## Troubleshooting: log file location

Warnings and errors are written to `logs/downloads-sorter.log` in the app folder (rotating, gitignored). A crash on
startup also appends a traceback to `app_error.log` next to it.

## License

MIT — see [LICENSE](LICENSE).
