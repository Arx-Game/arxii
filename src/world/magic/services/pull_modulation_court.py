"""Court-role (COVENANT_ROLE) pull modulation: scale by the covenant leader's
signed NpcRegard for the live target, sign-directed by the effect's RegardPolarity (#1831).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.constants import COURT_REGARD_PULL_K, RegardPolarity

if TYPE_CHECKING:
    from evennia_extensions.models import ObjectDB
    from world.magic.models import Thread, ThreadPullEffect


def _resolve_court_leader_persona(thread: Thread):
    """The covenant leader's primary persona for the servant's engaged Court membership
    anchored on this thread's target_covenant_role; None if unresolved."""
    sheet = thread.owner  # Thread.owner is the CharacterSheet
    for m in sheet.character.covenant_roles.active_memberships:
        anchored_here = m.engaged and m.covenant_role_id == thread.target_covenant_role_id
        if anchored_here and m.covenant.leader_id:
            return m.covenant.leader.primary_persona
    return None


def _regard_polarity_matches(polarity: RegardPolarity, regard: int) -> bool:
    """Whether ``polarity`` matches the sign of a nonzero ``regard`` value.

    Shared by ``court_regard_modulation`` and the picker's
    ``_court_pull_would_have_effect`` (#1831) so the empower rule can't diverge
    between the two call sites. Callers are expected to have already
    short-circuited ``regard == 0`` before calling this.
    """
    return (
        (polarity == RegardPolarity.OFFENSIVE and regard < 0)
        or (polarity == RegardPolarity.PROTECTIVE and regard > 0)
        or (polarity == RegardPolarity.NEUTRAL)
    )


def court_regard_modulation(
    thread: Thread,
    target: ObjectDB,
    effect_row: ThreadPullEffect,
    base_scaled: int,
) -> int:
    """Empower ``base_scaled`` by the Court leader's signed regard for ``target``.

    Returns ``base_scaled`` unchanged when there is no resolvable leader, no
    target sheet, regard is 0, or the effect's ``RegardPolarity`` doesn't match
    the sign of the regard.
    """
    from world.npc_services.models import REGARD_MAX  # noqa: PLC0415
    from world.npc_services.regard import get_regard  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    leader_persona = _resolve_court_leader_persona(thread)
    if leader_persona is None:
        return base_scaled
    target_sheet = target.character_sheet
    if target_sheet is None:
        return base_scaled
    regard = get_regard(leader_persona, active_persona_for_sheet(target_sheet))
    if regard == 0:
        return base_scaled

    if not _regard_polarity_matches(effect_row.regard_polarity, regard):
        return base_scaled
    bonus = round(base_scaled * (abs(regard) / REGARD_MAX) * COURT_REGARD_PULL_K)
    return base_scaled + bonus
