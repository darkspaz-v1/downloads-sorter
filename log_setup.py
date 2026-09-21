"""Rotating-file logging shared by the app modules: logs/downloads-sorter.log (gitignored)."""
import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_PATH = LOG_DIR / "downloads-sorter.log"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(level=logging.INFO):
    """Attach a rotating file handler to the root logger (idempotent). Logging must
    never stop the app from starting, so an unwritable log dir just disables it."""
    root = logging.getLogger()
    if any(getattr(h, "_app_log", False) for h in root.handlers):
        return LOG_PATH
    try:
        LOG_DIR.mkdir(exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=256 * 1024, backupCount=3, encoding="utf-8"
        )
    except OSError:
        return None
    handler._app_log = True
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(level)
    return LOG_PATH
