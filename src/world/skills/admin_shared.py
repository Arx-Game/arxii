"""Skill admin pieces both the Skill and Trait admin pages use (#4820, #5008).

Here rather than in either admin module, so neither imports the other's (the
``world/societies/admin_inlines.py`` precedent). Nothing here registers an admin.
"""

from django.contrib import messages
from django.http import HttpRequest

from world.mechanics.services import ensure_skill_target
from world.traits.models import Trait


def ensure_skill_target_or_warn(request: HttpRequest, skill: Trait) -> None:
    """Make sure a modifier target points at ``skill``, warning staff if not (#4820).

    A skill rolls a distinction's bonus only through a stat-category ``ModifierTarget``
    whose ``target_trait`` is the skill; without one a pasted ``+10 <skill>`` is refused.
    An explicit call, not a signal (ADR-0009).
    """
    if ensure_skill_target(skill) is None:
        messages.warning(
            request,
            f"No modifier target was made for {skill.name}: another category already "
            "has a target of that name. Retarget that row to this skill on the "
            "Modifier targets admin.",
        )
