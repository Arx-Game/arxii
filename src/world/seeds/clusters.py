from __future__ import annotations

from collections.abc import Callable

from django.db.models import Model


def _seed_magic() -> None:
    from integration_tests.game_content.magic import seed_magic_dev  # noqa: PLC0415

    seed_magic_dev()


def _seed_items() -> None:
    from integration_tests.game_content.items import seed_items_dev  # noqa: PLC0415

    seed_items_dev()


def _seed_combat() -> None:
    from integration_tests.game_content.combat import (  # noqa: PLC0415
        seed_flee_check,
        seed_penetration_contest,
    )

    seed_penetration_contest()
    seed_flee_check()


def _seed_checks() -> None:
    from world.seeds.checks import seed_check_resolution_tables  # noqa: PLC0415

    seed_check_resolution_tables()


CLUSTER_SEEDERS: dict[str, Callable[[], None]] = {
    # The checks spine owns the global resolution charts/outcomes; seed it first
    # so the canonical rows exist before the other clusters run. (Idempotency
    # holds regardless of order — magic also ensures the spine itself.)
    "checks": _seed_checks,
    "magic": _seed_magic,
    "items": _seed_items,
    "combat": _seed_combat,
}


def seeded_models() -> list[type[Model]]:
    """Representative content models per cluster for row-count progress tracking."""
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.items.models import ItemTemplate  # noqa: PLC0415
    from world.magic.models import Affinity, Resonance  # noqa: PLC0415
    from world.traits.models import ResultChart  # noqa: PLC0415

    return [Affinity, Resonance, ItemTemplate, CheckType, ResultChart]
