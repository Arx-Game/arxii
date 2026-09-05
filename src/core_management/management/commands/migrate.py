"""``migrate`` with the generation guard in front (ADR-0272).

Wins resolution over Django's ``migrate`` because ``core_management`` is first in
INSTALLED_APPS (see the ORDER IS LOAD-BEARING comment in ``server/conf/settings.py``);
``core_management.tests.test_command_resolution`` pins it. django-linear-migrations
ships no ``migrate``, so there is no second override to subclass.

The guard is one SELECT on ``django_migrations``. It refuses the two states Django's
``replaces`` handling gets wrong: a database that recorded only part of the previous
generation (Django silently applies nothing) and one that never recorded the
previous generation at all (Django tries to CREATE every table). Production is
only ever "crossing" or "crossed", so the guard is a no-op there and a hard stop
anywhere else, before any schema is touched. Not a data migration; it moves no rows.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar

from django.core.management.base import CommandError
from django.core.management.commands.migrate import Command as MigrateCommand
from django.db import connections
from django.db.migrations.recorder import MigrationRecorder

from core_management.migration_generations import (
    APP_LABEL,
    GENERATIONS_PATH,
    classify_generation_state,
    load_generations,
)


class Command(MigrateCommand):
    GENERATION_GUARD_BYPASS_ENV: ClassVar[str] = "ARX_SKIP_GENERATION_GUARD"

    def handle(self, *args: Any, **options: Any) -> Any:
        if not os.environ.get(self.GENERATION_GUARD_BYPASS_ENV) and GENERATIONS_PATH.exists():
            connection = connections[options["database"]]
            recorded = {
                name
                for app, name in MigrationRecorder(connection).applied_migrations()
                if app == APP_LABEL
            }
            verdict = classify_generation_state(recorded, load_generations())
            if not verdict.ok:
                message = f"Migration generation guard: {verdict.message}"
                raise CommandError(message)
        return super().handle(*args, **options)
