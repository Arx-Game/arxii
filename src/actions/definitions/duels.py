"""Duel actions — PC-vs-PC challenge dispatch (#568).

Exposes:
- ``ChallengeAction``: issues a duel challenge to another character in the same room.
- ``AcceptChallengeAction``: challenged PC accepts a PENDING challenge.
- ``DeclineChallengeAction``: challenged PC declines a PENDING challenge.
- ``WithdrawChallengeAction``: challenger rescinds a PENDING challenge.
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
    from world.combat.models import DuelChallenge


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


def _pending_challenge_for_challenged(actor: ObjectDB) -> DuelChallenge | None:
    """Return the PENDING DuelChallenge where *actor* is the challenged PC, or None."""
    from world.combat.constants import DuelChallengeStatus  # noqa: PLC0415
    from world.combat.models import DuelChallenge  # noqa: PLC0415

    actor_sheet = _sheet(actor)
    if actor_sheet is None:
        return None
    return DuelChallenge.objects.filter(
        challenged_sheet=actor_sheet,
        status=DuelChallengeStatus.PENDING,
    ).first()


def _pending_challenge_for_challenger(actor: ObjectDB) -> DuelChallenge | None:
    """Return the PENDING DuelChallenge where *actor* is the challenger PC, or None."""
    from world.combat.constants import DuelChallengeStatus  # noqa: PLC0415
    from world.combat.models import DuelChallenge  # noqa: PLC0415

    actor_sheet = _sheet(actor)
    if actor_sheet is None:
        return None
    return DuelChallenge.objects.filter(
        challenger_sheet=actor_sheet,
        status=DuelChallengeStatus.PENDING,
    ).first()


@dataclass
class AcceptChallengeAction(Action):
    """Accept a PENDING duel challenge directed at this PC.

    Only the *challenged* PC may accept.  Resolves the actor's PENDING incoming
    challenge, creates a CombatEncounter, and returns the encounter ID.
    """

    key: str = "accept"
    name: str = "Accept Duel"
    icon: str = "check"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_sheet = _sheet(actor)
        if actor_sheet is None:
            return ActionResult(
                success=False,
                message="You must be a real character to accept a duel challenge.",
            )

        challenge = _pending_challenge_for_challenged(actor)
        if challenge is None:
            return ActionResult(
                success=False,
                message="You have no pending duel challenge to accept.",
            )

        from world.combat.duels import accept_challenge  # noqa: PLC0415

        try:
            encounter = accept_challenge(challenge)
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        return ActionResult(
            success=True,
            message="You accept the duel challenge.",
            data={"challenge_id": challenge.pk, "encounter_id": encounter.pk},
        )


@dataclass
class DeclineChallengeAction(Action):
    """Decline a PENDING duel challenge directed at this PC.

    Only the *challenged* PC may decline.  No encounter is created.
    """

    key: str = "decline"
    name: str = "Decline Duel"
    icon: str = "x"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_sheet = _sheet(actor)
        if actor_sheet is None:
            return ActionResult(
                success=False,
                message="You must be a real character to decline a duel challenge.",
            )

        challenge = _pending_challenge_for_challenged(actor)
        if challenge is None:
            return ActionResult(
                success=False,
                message="You have no pending duel challenge to decline.",
            )

        from world.combat.duels import decline_challenge  # noqa: PLC0415

        try:
            decline_challenge(challenge)
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        return ActionResult(
            success=True,
            message="You decline the duel challenge.",
            data={"challenge_id": challenge.pk},
        )


@dataclass
class WithdrawChallengeAction(Action):
    """Withdraw a PENDING duel challenge this PC issued.

    Only the *challenger* may withdraw.  No encounter is created.
    """

    key: str = "withdraw"
    name: str = "Withdraw Challenge"
    icon: str = "undo"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_sheet = _sheet(actor)
        if actor_sheet is None:
            return ActionResult(
                success=False,
                message="You must be a real character to withdraw a duel challenge.",
            )

        challenge = _pending_challenge_for_challenger(actor)
        if challenge is None:
            return ActionResult(
                success=False,
                message="You have no pending duel challenge to withdraw.",
            )

        from world.combat.duels import withdraw_challenge  # noqa: PLC0415

        try:
            withdraw_challenge(challenge)
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        return ActionResult(
            success=True,
            message="You withdraw your duel challenge.",
            data={"challenge_id": challenge.pk},
        )


# Module-level singletons — registered in actions/registry.py
accept = AcceptChallengeAction()
decline = DeclineChallengeAction()
withdraw = WithdrawChallengeAction()
