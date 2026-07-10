"""Idempotent seed helpers for the projects framework.

Per repo discipline (#683): seeds live in code, called via
``get_or_create``/``update_or_create`` — NOT a committed fixture.
"""

from __future__ import annotations

from world.projects.constants import ProjectKind
from world.projects.models import ProjectKindResonanceAward


def ensure_project_kind_resonance_awards() -> None:
    """Seed the PROJECT_CONTRIBUTION opt-in table (#2038).

    Only ``ORGANIZATION_CAPABILITY`` opts in today ("projects to add gifts to
    organizations" per Tehom's ruling) — conservative, flat +5 resonance per
    contribution, sized between ``ResonanceGainConfig``'s existing per-action
    flat grants (``scene_entry_grant=4``, ``style_presentation_grant=4``,
    ``entry_flourish_grant=10``): contributing to an org's magical capability is a
    slower, session-spanning group project, not a single social beat.

    ``get_or_create`` (not ``update_or_create``) so a staff-tuned amount already in
    the DB survives a re-run of this seeder untouched — only a missing row is
    created. Future ritual-type ``ProjectKind`` values opt in with an authored row
    (staff admin or a future seed addition), no code change.
    """
    ProjectKindResonanceAward.objects.get_or_create(
        kind=ProjectKind.ORGANIZATION_CAPABILITY,
        defaults={"resonance_award_amount": 5},
    )
