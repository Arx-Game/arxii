"""Fail when any first-party app's models drifted from its migrations.

Scopes makemigrations --check to LOCAL apps (those under src/) so the
pre-existing phantom Evennia-library proxy-model changes — which
core_management's custom makemigrations filters only at write time — can't
trip the gate. Used by CI (ty job) and the nightly migration-replay workflow.
"""

import os
from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parent.parent / "src"


def main() -> None:
    os.chdir(SRC_DIR)
    sys.path.insert(0, str(SRC_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")

    import django  # noqa: PLC0415

    django.setup()

    from django.apps import apps  # noqa: PLC0415
    from django.core.management import call_command  # noqa: PLC0415

    src_prefix = str(SRC_DIR)
    local_labels = sorted(
        cfg.label for cfg in apps.get_app_configs() if cfg.path.startswith(src_prefix)
    )
    call_command("makemigrations", *local_labels, check=True, dry_run=True, verbosity=1)


if __name__ == "__main__":
    main()
