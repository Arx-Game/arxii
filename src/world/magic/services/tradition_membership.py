"""Tradition membership lifecycle services (#2441).

The in-play join/leave/switch seam for ``CharacterTradition``, wired from the
org-membership accept flow (ruling 1 on #2441 — a tradition is joined through its
teaching org's ``OrganizationMembershipOffer`` accept flow,
``world.societies.membership_services.accept_invitation``/``accept_application``).

``CharacterTradition.left_at`` (added by this task) makes switching history-preserving
(ruling 2): the old row is ended, never deleted, and a new one created. Learned
techniques are untouched (ruling 3 — "learned is learned"; only future signature-list
*access* changes, via ``world.npc_services.effects._technique_available_to_learner``'s
active-only filter). Joining a living tradition sheds the Unbound/Orphaned-Tradition
drawback distinction automatically; leaving re-applies Unbound (ruling 4 — symmetric
and automatic).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.magic.exceptions import AlreadyInTraditionError, NoActiveTraditionError

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import CharacterTradition, Tradition
    from world.societies.models import OrganizationMembership

logger = logging.getLogger(__name__)

#: Drawback-distinction slugs that mark a character as traditionless-in-play
#: (#2441 ruling 4). "orphaned-tradition" is seeded today
#: (``world.seeds.character_creation.ensure_orphaned_tradition_distinction``, #2428
#: Task 5); "unbound" is Task 9's addition — this constant tolerates its absence
#: (see ``_shed_traditionless_drawbacks``). Both are removed on joining a
#: non-orphaned tradition.
_SHED_ON_JOIN_SLUGS = ("unbound", "orphaned-tradition")

#: Only "unbound" is re-applied on leave — an ex-Orphaned-Tradition-drawback
#: character who leaves their (already orphaned) tradition becomes plain Unbound,
#: not doubly-drawbacked with a stale Orphaned-Tradition row pointing at a
#: tradition they no longer belong to.
_REAPPLY_ON_LEAVE_SLUG = "unbound"


def _active_tradition_row(sheet: CharacterSheet) -> CharacterTradition | None:
    """Return the character's active (``left_at IS NULL``) CharacterTradition row, or None."""
    from world.magic.models import CharacterTradition  # noqa: PLC0415

    return CharacterTradition.objects.filter(character=sheet, left_at__isnull=True).first()


def _tradition_is_orphaned(tradition: Tradition) -> bool:
    """Whether ``tradition`` currently has no living teachers (#2441).

    Task 5 (#2428) modeled "orphaned" as a CG-selection gate, not a live field on
    ``Tradition``: a ``BeginningTradition`` row requires the "Orphaned Tradition"
    drawback distinction (``required_distinction``) before a tradition with no
    living trainers can be picked at CG (see ``world.seeds.character_creation.
    ensure_orphaned_tradition_distinction``/``seed_metallic_order_tradition``). That
    authored gate is the only place "this tradition lacks teachers" is recorded
    anywhere in the schema, so it doubles as the live-game truth read here — the
    smallest truthful check available without inventing a parallel field Task 5
    didn't build (verified: no "orphan"/"is_orphaned" surface exists anywhere in
    ``world.magic`` or ``world.npc_services``). A lazy import keeps ``magic`` from
    taking a module-level dependency on ``character_creation`` (documented as a
    "CG-only concern" on ``BeginningTradition`` itself — this is the one read that
    deliberately reaches back across that boundary for a live-game answer).
    """
    from world.character_creation.models import BeginningTradition  # noqa: PLC0415

    return BeginningTradition.objects.filter(
        tradition=tradition,
        required_distinction__slug="orphaned-tradition",
    ).exists()


def _shed_traditionless_drawbacks(sheet: CharacterSheet) -> None:
    """Delete any held unbound/orphaned-tradition drawback CharacterDistinction rows.

    Direct queryset delete — ``world.distinctions.services`` has no removal
    counterpart to ``grant_distinction`` (verified for #2441 Task 8: the only
    writers of ``CharacterDistinction`` are ``grant_distinction``, CG
    finalization, and Django admin; nothing in the codebase revokes one). A
    drawback flag carries no story-significant history worth preserving as a row
    (contrast ``CharacterTradition`` itself, which is ``left_at``-preserved) — a
    plain delete mirrors how other short-lived/no-longer-true rows are cleaned up
    elsewhere in this codebase (e.g. expired offer rows). Tolerates either/both
    slugs being absent (Task 9 seeds "unbound"; this task only ships
    "orphaned-tradition").
    """
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

    CharacterDistinction.objects.filter(
        character=sheet,
        distinction__slug__in=_SHED_ON_JOIN_SLUGS,
    ).delete()


def _reapply_unbound_drawback(sheet: CharacterSheet) -> None:
    """Re-grant the "unbound" drawback distinction on leaving a tradition (#2441 ruling 4).

    Defensive skip (logged) if the "unbound" Distinction row doesn't exist yet —
    Task 9 seeds it, and this task's ``leave_tradition`` must not hard-fail on a
    DB that hasn't run that seed yet. Catches ``DistinctionExclusionError`` and
    skips (logs) rather than propagating, per the ``grant_distinction`` seam's
    documented contract for non-GM/telnet callers (see
    ``world/distinctions/CLAUDE.md``: "every in-play caller except the GM
    action/telnet path catches it and skips just that grant").

    Uses ``DistinctionOrigin.GAMEPLAY`` — previously vestigial/unassigned (see
    ``world.distinctions.types.DistinctionOrigin``'s docstring, updated alongside
    this change) — since none of the four previously-ratified sources
    (``GM_AWARD``/``ACHIEVEMENT_AUTO_GRANT``/``CONSEQUENCE_POOL``/
    ``ENDORSEMENT_THRESHOLD``) describes an automatic system consequence of a
    player's own leave-tradition action.
    """
    from world.distinctions.exceptions import DistinctionExclusionError  # noqa: PLC0415
    from world.distinctions.models import Distinction  # noqa: PLC0415
    from world.distinctions.services import grant_distinction  # noqa: PLC0415
    from world.distinctions.types import DistinctionOrigin  # noqa: PLC0415

    distinction = Distinction.objects.filter(slug=_REAPPLY_ON_LEAVE_SLUG).first()
    if distinction is None:
        logger.info(
            "leave_tradition: %r drawback distinction not seeded yet (#2441 Task 9) "
            "— skipping re-application for character sheet #%s.",
            _REAPPLY_ON_LEAVE_SLUG,
            sheet.pk,
        )
        return

    try:
        grant_distinction(
            sheet,
            distinction,
            origin=DistinctionOrigin.GAMEPLAY,
            source_description="Left your tradition — Unbound once again.",
        )
    except DistinctionExclusionError:
        logger.warning(
            "leave_tradition: re-applying %r blocked by exclusion conflict on "
            "character sheet #%s — skipping.",
            _REAPPLY_ON_LEAVE_SLUG,
            sheet.pk,
        )


@transaction.atomic
def join_tradition(
    sheet: CharacterSheet,
    tradition: Tradition,
    *,
    via_membership: OrganizationMembership | None = None,
) -> CharacterTradition:
    """Join (or switch to) a Tradition, preserving history (#2441 rulings 1/2).

    Ends the character's current active ``CharacterTradition`` row (if any) by
    stamping ``left_at``, then creates a new active row for ``tradition``. Refuses
    as a no-op re-join (raises ``AlreadyInTraditionError``) when ``tradition`` is
    already the character's active tradition — mirrors ``join_organization``'s
    ``AlreadyOrganizationMemberError`` refusal shape.

    Learned techniques are untouched (ruling 3 — "learned is learned"); only
    future signature-list *access* changes
    (``world.npc_services.effects._technique_available_to_learner`` reads active
    membership only, via ``left_at__isnull=True``).

    Joining a tradition that is NOT orphaned (``_tradition_is_orphaned``) sheds any
    held Unbound/Orphaned-Tradition drawback distinction (ruling 4) — no
    retroactive CG benefits, just forward-looking access. Joining an orphaned
    tradition keeps the drawback: the character is still without living teachers.

    ``via_membership`` is the triggering ``OrganizationMembership`` when this call
    originates from the org-membership accept flow (ruling 1) — used only to name
    the joining organization in the narrative message; not persisted on the row
    (no such FK was requested for this task — provenance beyond the narrative line
    is out of scope).
    """
    from world.magic.models import CharacterTradition  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    active = _active_tradition_row(sheet)
    if active is not None and active.tradition_id == tradition.pk:
        raise AlreadyInTraditionError

    if active is not None:
        active.left_at = timezone.now()
        active.save(update_fields=["left_at"])

    new_row = CharacterTradition.objects.create(character=sheet, tradition=tradition)

    if not _tradition_is_orphaned(tradition):
        _shed_traditionless_drawbacks(sheet)

    if via_membership is not None:
        body = (
            f"You have joined {tradition.name} through your membership in "
            f"{via_membership.organization.name}."
        )
    else:
        body = f"You have joined {tradition.name}."
    send_narrative_message(
        recipients=[sheet],
        body=body,
        category=NarrativeCategory.ABILITY,
        sender_account=None,
    )

    return new_row


@transaction.atomic
def leave_tradition(sheet: CharacterSheet) -> CharacterTradition:
    """Leave the character's active Tradition, becoming traditionless-in-play.

    Sets ``left_at`` on the active row only — no replacement row is created (see
    #2441's "New surfaces" section). Raises ``NoActiveTraditionError`` if the
    character has no active tradition to leave (already traditionless).

    Re-applies the "unbound" drawback distinction (spec default ruling — #2441's
    ``leave_tradition`` surface note: "traditionless is traditionless"). Defensive
    no-op (logged) if that distinction isn't seeded yet — Task 9 ships it.

    No live caller wires this yet — #2441 Task 8's scope covers only the join
    direction, triggered by the org-membership accept flow. A natural future
    wiring point is a tradition-org ``leave_organization``/``expel_member`` hook,
    symmetric with the join wiring; that call was left to a later task/design pass
    rather than assumed here (see intent-provenance note in the Task 8 report).
    """
    active = _active_tradition_row(sheet)
    if active is None:
        raise NoActiveTraditionError

    active.left_at = timezone.now()
    active.save(update_fields=["left_at"])

    _reapply_unbound_drawback(sheet)

    return active
