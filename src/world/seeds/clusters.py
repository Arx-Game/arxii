from __future__ import annotations

from collections.abc import Callable


def _seed_magic() -> None:
    from integration_tests.game_content.magic import seed_magic_dev  # noqa: PLC0415

    seed_magic_dev()


def _seed_items() -> None:
    from integration_tests.game_content.items import seed_items_dev  # noqa: PLC0415

    seed_items_dev()


CLUSTER_SEEDERS: dict[str, Callable[[], None]] = {
    "magic": _seed_magic,
    "items": _seed_items,
}


def seeded_models() -> list:
    """Models whose row counts approximate seed progress (expanded in Task 2)."""
    from world.magic.models import Affinity, Resonance  # noqa: PLC0415

    return [Affinity, Resonance]
