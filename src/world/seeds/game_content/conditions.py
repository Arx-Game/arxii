"""ConditionContent — named social conditions applied by social action consequences."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.conditions.models import ConditionTemplate

# Canonical social condition names — each maps to the action that inflicts it.
SHAKEN = "Shaken"  # intimidate
CHARMED = "Charmed"  # persuade
DECEIVED = "Deceived"  # deceive
SMITTEN = "Smitten"  # flirt
CAPTIVATED = "Captivated"  # perform
ENTHRALLED = "Enthralled"  # entrance

_SOCIAL_CONDITIONS: list[tuple[str, str]] = [
    (SHAKEN, "The target is rattled and acts with less confidence."),
    (CHARMED, "The target feels unusually well-disposed toward the initiator."),
    (DECEIVED, "The target has been successfully misled."),
    (SMITTEN, "The target is emotionally captivated by the initiator."),
    (CAPTIVATED, "The target is held rapt by the initiator's performance."),
    (ENTHRALLED, "The target is wholly compelled by the initiator's presence."),
]


class ConditionContent:
    """Creates the 6 named social conditions used by social action consequences."""

    @staticmethod
    def create_all() -> dict[str, ConditionTemplate]:
        """Create all 6 social conditions via ConditionTemplateFactory.

        Uses django_get_or_create — safe to call from multiple test classes.

        Returns:
            Dict mapping condition name to ConditionTemplate instance.
        """
        from world.conditions.factories import (  # noqa: PLC0415
            ConditionCategoryFactory,
            ConditionTemplateFactory,
        )

        social_cat = ConditionCategoryFactory(name="Social")
        conditions: dict[str, ConditionTemplate] = {}
        for name, description in _SOCIAL_CONDITIONS:
            conditions[name] = ConditionTemplateFactory(
                name=name,
                category=social_cat,
                description=description,
            )
        return conditions
