"""CheckContent — thin wrapper around existing social check/action template factories.

Calls the canonical factory helpers so tests reuse the same social check types
and action templates without duplicating definitions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actions.models.action_templates import ActionTemplate
    from world.checks.models import CheckType


class CheckContent:
    """Thin wrapper around the social check/action template factory helpers."""

    @staticmethod
    def create_check_types() -> dict[str, CheckType]:
        """Create the 6 social CheckTypes (and their trait weights).

        Returns:
            Dict mapping check type name to CheckType instance.
        """
        from world.checks.factories import create_social_check_types  # noqa: PLC0415

        return create_social_check_types()

    @staticmethod
    def create_action_templates() -> list[ActionTemplate]:
        """Create the 6 social ActionTemplates (calls create_check_types internally).

        Returns:
            List of ActionTemplate instances.
        """
        from world.checks.factories import create_social_action_templates  # noqa: PLC0415

        return create_social_action_templates()
