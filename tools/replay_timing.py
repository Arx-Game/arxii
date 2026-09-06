"""Replay the migration chain against DATABASE_URL and report wall time + peak RSS.

Used by ``just verify-regeneration`` and by hand when benchmarking (ADR-0276). Runs
Django's ``migrate`` in-process so ``resource.getrusage`` sees the real peak; the
numbers are what to compare against the 2026-09-05 baseline of the generation-1
chain on a dev box: 48m06s and about 2.6 GB.

A plain ``python`` entry point on purpose: ``arx`` re-reads ``src/.env`` with
override, which would silently send the replay at the dev database instead of
the scratch one named in ``DATABASE_URL``.
"""

from __future__ import annotations

import os
from pathlib import Path
import resource
import sys
import time

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def main() -> int:
    os.chdir(SRC_DIR)
    sys.path.insert(0, str(SRC_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")
    import django  # noqa: PLC0415

    django.setup()
    from django.core.management import call_command  # noqa: PLC0415

    start = time.monotonic()
    call_command("migrate", interactive=False, verbosity=1)
    elapsed = time.monotonic() - start
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    print(f"replay_seconds={elapsed:.0f} peak_rss_mb={peak_mb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
