"""Canonical content-repo path resolution (#2448).

Single source of truth for locating the private lore-repo checkout that the
export/push/import pipeline (``content_export``, ``content_push``,
``grid_export``, ``grid_import``, the admin views) and the ``tools/`` CLI
wrappers all need. Before this module existed, four call sites each carried
their own copy of this lookup (``content_export.py``, ``content_push.py``,
``web/admin/content_load_views.py``, ``web/admin/content_push_views.py``)
plus three near-identical ``tools/*.py`` dotenv-fallback copies — this
consolidates all of them.

Two entry points, because the two calling contexts differ:

- ``resolve_content_root()`` — the runtime lookup used by everything that
  runs inside an already-configured process (service functions, admin
  views): reads ``CONTENT_REPO_PATH`` straight from ``os.environ`` (already
  loaded into the process by the ``arx`` CLI's dotenv handling) and
  validates it names a real directory.
- ``load_dotenv_content_path()`` — the standalone lookup for the
  ``tools/*.py`` CLI wrappers, which run *before* Django is configured (and
  sometimes before the ``arx`` CLI's dotenv loading has happened at all):
  falls back to parsing ``src/.env`` directly for ``CONTENT_REPO_PATH`` when
  the variable isn't already in the environment. Returns the raw string
  (unvalidated, unexpanded) so callers can report a not-found path back to
  the user the same way the pre-consolidation copies did.

Import-safe without Django configured — no Django imports anywhere in this
module, ever (the tools scripts import this before ``django.setup()`` runs).
"""

from __future__ import annotations

import os
from pathlib import Path

#: This file lives at src/core_management/content_repo.py — parent.parent is src/.
_SRC_ROOT = Path(__file__).resolve().parent.parent


def resolve_content_root() -> Path | None:
    """Return the configured content-repo path if set and a real directory."""
    raw = os.environ.get("CONTENT_REPO_PATH")
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_dir():
        return None
    return path


def load_dotenv_content_path() -> str | None:
    """Read CONTENT_REPO_PATH from the environment, falling back to src/.env.

    Standalone-usable (no Django import, no directory-existence check) — the
    ``tools/*.py`` CLI wrappers call this to get a raw path string before
    Django is configured, then validate/report on it themselves.
    """
    value = os.environ.get("CONTENT_REPO_PATH")
    if value:
        return value
    env_file = _SRC_ROOT / ".env"
    if env_file.is_file():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("CONTENT_REPO_PATH="):
                return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None
