"""Shared constants and choices for the Missions system (Phase 1).

TextChoices live here (not as nested model classes) so serializers and the
affordance-resolution service can reference them without circular imports.
"""

from django.db import models


class OptionProduces(models.TextChoices):
    """What an :class:`~world.missions.models.AffordanceBinding` yields.

    A binding either surfaces a narrative BRANCH (no dice — the descriptor
    simply unlocks a path) or a CHECK (resolved by a ``checks.CheckType``
    with an authored base risk).
    """

    BRANCH = "branch", "Branch"
    CHECK = "check", "Check"
