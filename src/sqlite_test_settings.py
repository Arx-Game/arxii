"""
Windows parallel-worker shim for ``sqlite_test_settings``.

Mirrors ``src/test_settings.py``. The real settings live at
``server.conf.sqlite_test_settings``; this shim re-exports them so parallel
test workers (which inherit ``DJANGO_SETTINGS_MODULE=sqlite_test_settings``
as a bare name) can resolve it via ``src/`` on sys.path.

See ``src/test_settings.py`` for the full rationale.
"""

from server.conf.sqlite_test_settings import *  # noqa: F403
