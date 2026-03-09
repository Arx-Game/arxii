"""Handlers for the achievements system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import F

if TYPE_CHECKING:
    from world.achievements.models import StatDefinition, StatTracker
    from world.character_sheets.models import CharacterSheet


def _get_stat_tracker_model() -> type[StatTracker]:
    """Lazy import to avoid circular dependency."""
    from world.achievements.models import StatTracker  # noqa: PLC0415

    return StatTracker


class StatHandler:
    """
    Cached stat tracker for a character sheet.

    Lazily loads all stat values on first access, then serves from cache.
    Mutations update both the database and the local cache.

    Attached to CharacterSheet as a @cached_property so the cache persists
    for the lifetime of the model instance.
    """

    def __init__(self, character_sheet: CharacterSheet) -> None:
        self._character_sheet = character_sheet
        self._cache: dict[int, int] | None = None

    def _load(self) -> None:
        """Load all stat values for this character into the cache."""
        if self._cache is None:
            model = _get_stat_tracker_model()
            self._cache = dict(
                model.objects.filter(character_sheet=self._character_sheet).values_list(
                    "stat_id", "value"
                )
            )

    def get(self, stat: StatDefinition) -> int:
        """Return current value of a stat, 0 if not tracked."""
        self._load()
        return self._cache.get(stat.pk, 0)  # type: ignore[union-attr]

    def increment(self, stat: StatDefinition, amount: int = 1) -> int:
        """
        Increment a stat (create if needed) and check for achievements.

        Uses F() for atomic DB increment, then updates the local cache.
        Returns the new value.
        """
        model = _get_stat_tracker_model()

        tracker, created = model.objects.get_or_create(
            character_sheet=self._character_sheet,
            stat=stat,
            defaults={"value": amount},
        )
        if not created:
            model.objects.filter(pk=tracker.pk).update(value=F("value") + amount)
            tracker.flush_from_cache(force=True)
            tracker = model.objects.get(pk=tracker.pk)

        # Update local cache
        self._load()
        self._cache[stat.pk] = tracker.value  # type: ignore[index]

        # Check for newly met achievement requirements
        from world.achievements.services import _check_achievements  # noqa: PLC0415

        _check_achievements(self._character_sheet, stat)

        return tracker.value
