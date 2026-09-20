# Downloads Sorter

Keeps the Downloads folder from turning into a junk drawer, without any interaction.

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

## Running it

```
run.bat
```

That creates the virtualenv on first run, installs `requirements.txt`, and starts the app. Windows
only — these use Win32 APIs and a system tray.

## License

MIT — see [LICENSE](LICENSE).
