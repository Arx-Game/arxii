"""The four Evennia log files, derived from one directory.

Evennia computes SERVER_LOG_FILE, PORTAL_LOG_FILE, HTTP_LOG_FILE and
LOCKWARNING_LOG_FILE from *its own* LOG_DIR at import time
(evennia/settings_default.py). settings.py overrides LOG_DIR from the
environment, so it must recompute all four from the new value; setting
LOG_DIR alone moves nothing. This module is the one place that knows the
file names, so the derivation is testable without re-importing settings.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LogFilePaths:
    """Absolute paths of the four log files Evennia writes."""

    server: str
    portal: str
    http: str
    lockwarning: str


def log_file_paths(log_dir: str) -> LogFilePaths:
    """Return the four Evennia log-file paths inside ``log_dir``.

    The file names match evennia/settings_default.py exactly.
    """
    base = Path(log_dir)
    return LogFilePaths(
        server=str(base / "server.log"),
        portal=str(base / "portal.log"),
        http=str(base / "http_requests.log"),
        lockwarning=str(base / "lockwarnings.log"),
    )
