"""Duel actions — PC-vs-PC challenge dispatch (#568).

Exposes a single ``ChallengeAction`` that issues a duel challenge to another
character in the same room, subject to the social-consent gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.types import ActionContext, ActionResult, TargetFilters, TargetType

_CHALLENGE_TARGET_FILTERS = TargetFilters(in_same_scene=True, exclude_self=True)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet


def _sheet(actor: ObjectDB) -> CharacterSheet | None:
    """Return *actor*'s CharacterSheet, or None if absent."""
    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def _active_tenure(sheet: CharacterSheet) -> object | None:
    """Return the current (active) RosterTenure for *sheet*, or None."""
    try:
        entry = sheet.roster_entry  # OneToOne reverse — may raise RelatedObjectDoesNotExist
    except ObjectDoesNotExist:
        return None
    return entry.current_tenure


def _consent_blocked(target_sheet: CharacterSheet, actor_sheet: CharacterSheet) -> bool:
    """Return True if *target_sheet*'s consent preference blocks *actor_sheet*.

    Delegates to ``_tenure_blocks_actor`` from ``actions.player_interface``,
    which already owns the SocialConsentPreference / whitelist logic (#544).

    Returns False when the target has no active tenure — no preference means
    allow (consistent with how ``_tenure_blocks_actor`` treats a missing pref).
    """
    from actions.player_interface import _tenure_blocks_actor  # noqa: PLC0415

    target_tenure = _active_tenure(target_sheet)
    if target_tenure is None:
        return False  # No active tenure → no consent preference → allow
    actor_tenure = _active_tenure(actor_sheet)
    return _tenure_blocks_actor(target_tenure, actor_tenure)


def create_challenge(
    challenger_sheet: CharacterSheet,
    challenged_sheet: CharacterSheet,
    room: ObjectDB,
) -> object:
    """Create and return a PENDING DuelChallenge.

    Thin service wrapper — all validation is done by the action before this
    is called.  Kept here (rather than inlined in execute) so future callers
    (e.g. a telnet command) can reuse the creation seam.
    """
    from world.combat.models import DuelChallenge  # noqa: PLC0415

    return DuelChallenge.objects.create(
        challenger_sheet=challenger_sheet,
        challenged_sheet=challenged_sheet,
        room=room,
    )


@dataclass
class ChallengeAction(Action):
    """Issue a PC-vs-PC duel challenge to a character in the same room.

    Social-consent gate: if the target's SocialConsentPreference blocks the
    challenger (or requires whitelist inclusion), the action fails before
    creating any DuelChallenge row.

    Both participants must have a PRIMARY persona (ensured by CharacterSheet)
    and be in the same room.  Self-challenge is rejected.
    """

    key: str = "challenge"
    name: str = "Challenge"
    icon: str = "swords"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind = TargetKind.CHARACTER
    target_filters: TargetFilters = field(default=_CHALLENGE_TARGET_FILTERS)

    def execute(  # noqa: PLR0911
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target: ObjectDB | None = kwargs.get("target")

        # --- resolve actor sheet ---
        actor_sheet = _sheet(actor)
        if actor_sheet is None:
            return ActionResult(
                success=False,
                message="You must be a real character to issue a duel challenge.",
            )

        # --- target required ---
        if target is None:
            return ActionResult(success=False, message="Challenge whom?")

        # --- no self-challenge ---
        if target.pk == actor.pk:
            return ActionResult(success=False, message="You cannot challenge yourself to a duel.")

        # --- same room ---
        actor_room = actor.db_location
        target_room = target.db_location
        if actor_room is None or target_room is None or actor_room.pk != target_room.pk:
            return ActionResult(
                success=False,
                message="You can only challenge someone in the same room.",
            )

        # --- target must have a character sheet (is a real PC) ---
        target_sheet = _sheet(target)
        if target_sheet is None:
            return ActionResult(
                success=False,
                message="You can only challenge a real character to a duel.",
            )

        # --- social-consent gate ---
        if _consent_blocked(target_sheet, actor_sheet):
            return ActionResult(
                success=False,
                message=(
                    f"{target.db_key} has opted out of social targeting and cannot be challenged."
                ),
            )

        # --- create the PENDING challenge ---
        challenge = create_challenge(actor_sheet, target_sheet, actor_room)

        return ActionResult(
            success=True,
            message=f"You issue a duel challenge to {target.db_key}.",
            data={"challenge_id": challenge.pk},
        )


# Module-level singleton — registered in actions/registry.py
challenge = ChallengeAction()
