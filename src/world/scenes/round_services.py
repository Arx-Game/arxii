"""Lifecycle services for non-combat scene rounds."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from world.scenes.constants import (
    ACTIVE_SCENE_ROUND_STATUSES,
    RoundStatus,
    SceneRoundMode,
    SceneRoundParticipantStatus,
    SceneRoundStartReason,
)
from world.scenes.models import SceneActionDeclaration, SceneRound, SceneRoundParticipant
from world.vitals.services import tick_round_for_targets

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.mechanics.models import ChallengeApproach, ChallengeInstance
    from world.mechanics.types import ChallengeResolutionResult

logger = logging.getLogger(__name__)


def _validate_reactive_declaration(
    participant: SceneRoundParticipant,
    ally: SceneRoundParticipant,
    *,
    label: str,
    self_target_message: str,
) -> None:
    """Shared guard chain for declare_succor_scene/declare_interpose_scene.

    Raises ``ValueError`` with an action-specific message on the first violated
    precondition: cross-round mismatch, self-targeting, an inactive caller, or an
    inactive ally — in that order. ``label`` (``"Succor"``/``"Interpose"``) names the
    maneuver in the target-related messages; ``self_target_message`` carries the
    "Cannot X yourself"/"Cannot X for yourself" wording, which differs between the
    two callers (kept as a caller-supplied string rather than derived from ``label``).
    """
    if participant.scene_round_id != ally.scene_round_id:
        msg = f"{label} target must be in the same scene round."
        raise ValueError(msg)
    if ally.pk == participant.pk:
        raise ValueError(self_target_message)
    if participant.status != SceneRoundParticipantStatus.ACTIVE:
        msg = f"Cannot {label.lower()}: you are not an active participant in this round."
        raise ValueError(msg)
    if ally.status != SceneRoundParticipantStatus.ACTIVE:
        msg = f"{label} target must be an active participant in this round."
        raise ValueError(msg)


def declare_succor_scene(
    participant: SceneRoundParticipant,
    ally: SceneRoundParticipant,
) -> SceneActionDeclaration:
    """Declare Succor for a scene round — the non-combat sibling of declare_succor (#1744).

    Always names a specific ally (see world.combat.services.declare_succor's
    docstring for why). Writable during an open STRICT declaration window only.
    """
    _validate_reactive_declaration(
        participant, ally, label="Succor", self_target_message="Cannot succor yourself."
    )

    scene_round = participant.scene_round
    declaration, _ = SceneActionDeclaration.objects.update_or_create(
        scene_round=scene_round,
        round_number=scene_round.round_number,
        participant=participant,
        is_immediate=False,
        defaults={
            "succor_target": ally,
            "succor_resolution": None,
            "is_pass": False,
            "challenge_instance": None,
            "challenge_approach": None,
        },
    )
    return declaration


def declare_interpose_scene(
    participant: SceneRoundParticipant,
    ally: SceneRoundParticipant,
) -> SceneActionDeclaration:
    """Declare Interpose for a scene round — the non-combat sibling of declare_interpose (#1316).

    Named-ally only (mirrors declare_succor_scene's #1744 narrowing — see that function's
    docstring rationale). Writable during an open STRICT declaration window only.
    """
    _validate_reactive_declaration(
        participant,
        ally,
        label="Interpose",
        self_target_message="Cannot interpose for yourself.",
    )

    scene_round = participant.scene_round
    declaration, _ = SceneActionDeclaration.objects.update_or_create(
        scene_round=scene_round,
        round_number=scene_round.round_number,
        participant=participant,
        is_immediate=False,
        defaults={
            "interpose_target": ally,
            "is_pass": False,
            "challenge_instance": None,
            "challenge_approach": None,
        },
    )
    return declaration


class RoundModeError(ValueError):
    """Raised when set_scene_round_mode cannot apply the requested change."""


def set_scene_round_mode(
    scene_round: SceneRound,
    *,
    mode: str | None = None,
    advance_quorum_pct: int | None = None,
    max_actions_per_round: int | None = None,
    per_target_repeat_lock: bool | None = None,
) -> SceneRound:
    """Apply mode and/or knob changes to *scene_round* in-place.

    **Out-of-STRICT guard** (raises :class:`RoundModeError`): switching *away* from
    STRICT while a pending non-immediate declaration exists would orphan those
    declarations; the caller must force-resolve first.

    Only the supplied (non-None) fields are written; ``save(update_fields=...)``
    touches nothing else.
    """
    from world.scenes.models import SceneActionDeclaration  # noqa: PLC0415

    # Guard — switching away from STRICT with pending deferred declarations.
    leaving_strict = (
        scene_round.mode == SceneRoundMode.STRICT
        and mode is not None
        and mode != SceneRoundMode.STRICT
    )
    if (
        leaving_strict
        and SceneActionDeclaration.objects.filter(
            scene_round=scene_round, is_immediate=False
        ).exists()
    ):
        msg = "Resolve the current declarations first (force-resolve), then change the mode."
        raise RoundModeError(msg)

    update_fields: list[str] = []
    if mode is not None:
        scene_round.mode = mode
        update_fields.append("mode")
    if advance_quorum_pct is not None:
        scene_round.advance_quorum_pct = advance_quorum_pct
        update_fields.append("advance_quorum_pct")
    if max_actions_per_round is not None:
        scene_round.max_actions_per_round = max_actions_per_round
        update_fields.append("max_actions_per_round")
    if per_target_repeat_lock is not None:
        scene_round.per_target_repeat_lock = per_target_repeat_lock
        update_fields.append("per_target_repeat_lock")

    if update_fields:
        scene_round.save(update_fields=update_fields)

    # A knob change can make an in-flight DECLARING STRICT round newly complete (e.g. a GM
    # lowering advance_quorum_pct below the count of current declarers). Re-check
    # completion so the change takes effect immediately rather than waiting for the next
    # declaration (#1480). Safe no-op otherwise: maybe_resolve_scene_round guards on
    # status==DECLARING and scene_round_is_complete. OPEN/POSE_ORDER rounds are unaffected
    # (they tick immediately via _tick_scene_round_if_active, not via completion).
    if scene_round.mode == SceneRoundMode.STRICT and scene_round.status == RoundStatus.DECLARING:
        maybe_resolve_scene_round(scene_round)

    return scene_round


def active_round_for_room(room: ObjectDB) -> SceneRound | None:
    """Return the active (non-completed) SceneRound for a room, or None.

    One active round per room (the ``one_active_scene_round_per_room`` constraint),
    so ``.first()`` is unambiguous.
    """
    return SceneRound.objects.filter(room=room, status__in=ACTIVE_SCENE_ROUND_STATUSES).first()


def actions_this_round(scene_round: SceneRound, participant: SceneRoundParticipant) -> int:
    """Return the number of action declarations for a participant in the current round."""
    return scene_round.action_declarations.filter(
        round_number=scene_round.round_number, participant=participant
    ).count()


def distinct_actors_this_round(scene_round: SceneRound) -> int:
    """Return the number of distinct participants with declarations in the current round."""
    return (
        scene_round.action_declarations.filter(round_number=scene_round.round_number)
        .values("participant_id")
        .distinct()
        .count()
    )


@transaction.atomic
def record_pose_order_action(
    scene_round: SceneRound,
    participant: SceneRoundParticipant,
    target_persona: object = None,
) -> None:
    """Record an immediate (POSE_ORDER) action for a participant in the current round."""
    from world.scenes.models import SceneActionDeclaration  # noqa: PLC0415

    SceneActionDeclaration.objects.create(
        scene_round=scene_round,
        round_number=scene_round.round_number,
        participant=participant,
        target_persona=target_persona,
        is_immediate=True,
        is_pass=False,
    )


@transaction.atomic
def advance_pose_order_round_if_quorum(scene_round: SceneRound) -> SceneRound:
    """Advance round_number if distinct actors >= quorum. Pose-order rounds stay DECLARING."""
    import math  # noqa: PLC0415

    rnd = SceneRound.objects.select_for_update().get(pk=scene_round.pk)
    active = rnd.participants.filter(status=SceneRoundParticipantStatus.ACTIVE).count()
    if active == 0:
        return scene_round
    needed = math.ceil(rnd.advance_quorum_pct / 100 * active)
    if distinct_actors_this_round(rnd) >= needed:
        rnd.round_number += 1
        rnd.round_started_at = timezone.now()
        rnd.save(update_fields=["round_number", "round_started_at"])
        scene_round.refresh_from_db()
    return scene_round


@transaction.atomic
def start_scene_round(scene_round: SceneRound) -> SceneRound:
    """Advance a BETWEEN_ROUNDS round into DECLARING (round_number += 1)."""
    rnd = SceneRound.objects.select_for_update().get(pk=scene_round.pk)
    if rnd.status != RoundStatus.BETWEEN_ROUNDS:
        msg = f"Cannot start scene round: status is {rnd.status}, expected between_rounds."
        raise ValueError(msg)
    rnd.round_number += 1
    rnd.status = RoundStatus.DECLARING
    rnd.round_started_at = timezone.now()
    rnd.save(update_fields=["round_number", "status", "round_started_at"])
    scene_round.refresh_from_db()
    return scene_round


@transaction.atomic
def advance_scene_round(scene_round: SceneRound) -> SceneRound:
    """Resolve the current round: fire the shared END tick for all ACTIVE
    participants, then return to BETWEEN_ROUNDS.

    Resolving declared actions into outcomes is deferred to the acute-tier plan;
    this foundation drives only the effect tick.
    """
    rnd = SceneRound.objects.select_for_update().get(pk=scene_round.pk)
    if rnd.status != RoundStatus.DECLARING:
        msg = f"Cannot advance scene round: status is {rnd.status}, expected declaring."
        raise ValueError(msg)
    rnd.status = RoundStatus.RESOLVING
    rnd.save(update_fields=["status"])

    targets = [
        p.character_sheet.character
        for p in rnd.participants.filter(status=SceneRoundParticipantStatus.ACTIVE).select_related(
            "character_sheet__character"
        )
    ]
    tick_round_for_targets(targets, timing="end")

    rnd.status = RoundStatus.BETWEEN_ROUNDS
    rnd.save(update_fields=["status"])
    scene_round.refresh_from_db()
    return scene_round


@transaction.atomic
def end_scene_round(scene_round: SceneRound) -> SceneRound:
    """Mark a scene round COMPLETED."""
    rnd = SceneRound.objects.select_for_update().get(pk=scene_round.pk)
    rnd.status = RoundStatus.COMPLETED
    rnd.completed_at = timezone.now()
    rnd.save(update_fields=["status", "completed_at"])
    scene_round.refresh_from_db()
    return scene_round


@transaction.atomic
def advance_scene_round_for_action(scene_round: SceneRound) -> SceneRound:
    """Drive one tick of an OPEN/POSE_ORDER scene round in response to a participant's action.

    Cycles BETWEEN_ROUNDS -> DECLARING -> (tick) -> BETWEEN_ROUNDS, reusing the
    foundation lifecycle services. STRICT rounds (including danger rounds, which are
    always STRICT) never reach here — they resolve via the presence-gated
    ``maybe_resolve_scene_round`` path, which owns the danger auto-end.
    """
    rnd = SceneRound.objects.select_for_update().get(pk=scene_round.pk)
    if rnd.status == RoundStatus.BETWEEN_ROUNDS:
        start_scene_round(rnd)
        rnd.refresh_from_db()
    if rnd.status == RoundStatus.DECLARING:
        advance_scene_round(rnd)
        rnd.refresh_from_db()
    scene_round.refresh_from_db()
    return scene_round


def _danger_persists(scene_round: SceneRound) -> bool:
    """True while any ACTIVE participant still carries a danger-keeping condition.

    A DANGER round persists (keeps ticking) while a participant is Bleeding-Out or
    Plummeting (#1228) — the descent must keep advancing until the fall resolves
    (impact removes the Plummeting condition), then the round auto-ends.
    """
    from world.areas.positioning.constants import PLUMMETING_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.constants import BLEED_OUT_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    char_ids = list(
        scene_round.participants.filter(status=SceneRoundParticipantStatus.ACTIVE).values_list(
            "character_sheet__character_id", flat=True
        )
    )
    if not char_ids:
        return False
    return ConditionInstance.objects.filter(
        target_id__in=char_ids,
        condition__name__in=[BLEED_OUT_CONDITION_NAME, PLUMMETING_CONDITION_NAME],
    ).exists()


def _plummeting_character_ids(scene_round: SceneRound) -> set[int]:
    """Character ids of ACTIVE participants currently carrying the Plummeting condition.

    Used by ``resolve_scene_round`` to exempt fallers from the #1480 AFK own-peril
    skip: a fall is environmental and self-completing, so the descent advances on
    every END tick regardless of whether the faller declared an action this round.
    """
    from world.areas.positioning.constants import PLUMMETING_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    char_ids = list(
        scene_round.participants.filter(status=SceneRoundParticipantStatus.ACTIVE).values_list(
            "character_sheet__character_id", flat=True
        )
    )
    if not char_ids:
        return set()
    return set(
        ConditionInstance.objects.filter(
            target_id__in=char_ids,
            condition__name=PLUMMETING_CONDITION_NAME,
        ).values_list("target_id", flat=True)
    )


def _present_character_sheets(room: ObjectDB) -> list[CharacterSheet]:
    """CharacterSheets of characters currently in ``room`` (walks room.contents; no per-object query)."""  # noqa: E501
    present = []
    for obj in room.contents:
        try:
            sheet = obj.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            continue
        present.append(sheet)
    return present


@transaction.atomic
def ensure_round_for_acute_condition(character_sheet: CharacterSheet) -> SceneRound | None:
    """Ensure an active scene round exists for the character's room and enrol all present
    characters. Returns the round, or None if the character has no room.

    When no round is active, creates a **STRICT** ``SceneRound(start_reason=DANGER)`` —
    danger is no longer a separate round type, just an acute condition any active round
    ticks. When a round of any mode is already active (one active round per room), the
    peril simply rides that round. Caller guarantees the character is NOT in active combat.
    """
    room = character_sheet.character.location
    if room is None:
        return None
    rnd = SceneRound.objects.filter(room=room, status__in=ACTIVE_SCENE_ROUND_STATUSES).first()
    if rnd is None:
        rnd = SceneRound.objects.create(
            room=room,
            start_reason=SceneRoundStartReason.DANGER,
            mode=SceneRoundMode.STRICT,
        )
        start_scene_round(rnd)
        rnd.refresh_from_db()
    for sheet in _present_character_sheets(room):
        SceneRoundParticipant.objects.get_or_create(scene_round=rnd, character_sheet=sheet)
    return rnd


def scene_round_is_complete(scene_round: SceneRound) -> bool:
    """Quorum-gated completion: True when enough ACTIVE participants present in the room
    who *can act* have declared for the current round. The threshold is
    ``ceil(advance_quorum_pct / 100 × present_active_count)`` — the same field POSE_ORDER
    uses (``advance_pose_order_round_if_quorum``); at 100 it reduces to unanimity, so a
    GM/staff can still require everyone. Absent participants and present-but-``not
    can_act`` participants (e.g. an unconscious bleeding victim) are implicit passes
    (never block); an undeclared present ``can_act`` participant counts toward the
    denominator but not the declared count, so a quorum below 100 lets the round resolve
    without them — ending the AFK-stall deadlock (#1480). No timer — presence is the idle
    signal (AFK-safety); the AFK participant's own peril is skipped separately at
    resolution (see ``resolve_scene_round``)."""
    import math  # noqa: PLC0415

    from world.vitals.services import can_act  # noqa: PLC0415

    present_ids = {s.character_id for s in _present_character_sheets(scene_round.room)}
    active = scene_round.participants.filter(
        status=SceneRoundParticipantStatus.ACTIVE
    ).select_related("character_sheet")
    declared_ids = set(
        scene_round.action_declarations.filter(
            round_number=scene_round.round_number, is_immediate=False
        ).values_list("participant_id", flat=True)
    )
    present_active = [
        p
        for p in active
        if p.character_sheet.character_id in present_ids and can_act(p.character_sheet)
    ]
    if not present_active:
        return False  # nobody present and able to drive resolution
    needed = math.ceil(scene_round.advance_quorum_pct / 100 * len(present_active))
    declared_present_active = sum(1 for p in present_active if p.pk in declared_ids)
    return declared_present_active >= needed


def _resolve_downed_victim_peril(
    scene_round: SceneRound,
    present_ids: set[int],
    declared_ids: set[int],
) -> tuple[set[int], set[int]]:
    """Classify each downed victim's acute peril for this round (#1479).

    A downed victim is a present ACTIVE participant who cannot act yet carries an
    active acute-peril condition (Bleeding Out / Plummeting). For each one this
    stamps or clears the abandonment marker as a side effect and returns
    ``(downed_victim_participant_ids, advancing_participant_ids)``:

    - ``downed_victim_participant_ids`` — every downed victim found.
    - ``advancing_participant_ids`` — the subset whose peril SHOULD advance on the
      END tick because a hostile party drove this round.

    Called BEFORE ``_resolve_scene_declarations`` deletes the declaration rows, so
    ``hostile_drove_round`` can read this round's declarations.
    """
    from world.vitals.peril_resolution import (  # noqa: PLC0415
        acute_peril_instances,
        clear_abandoned,
        hostile_drove_round,
        mark_abandoned,
    )
    from world.vitals.services import can_act  # noqa: PLC0415

    downed_ids: set[int] = set()
    advancing_ids: set[int] = set()
    for p in scene_round.participants.filter(
        status=SceneRoundParticipantStatus.ACTIVE
    ).select_related("character_sheet__character"):
        sheet = p.character_sheet
        if sheet.character_id not in present_ids or can_act(sheet):
            continue
        if not acute_peril_instances(sheet).exists():
            continue
        downed_ids.add(p.pk)
        if hostile_drove_round(sheet, scene_round, declared_ids):
            advancing_ids.add(p.pk)
            clear_abandoned(sheet)
        else:
            mark_abandoned(sheet, scene_round)
    return downed_ids, advancing_ids


def _resolve_abandonment_grace(scene_round: SceneRound, held_ids: set[int]) -> None:
    """Resolve held downed victims who have waited out the abandonment grace window (#1479 T8).

    For each held (abandoned, non-advancing) downed victim whose acute-peril
    ``abandoned_since_round`` is set and ``round_number - abandoned_since_round >=
    abandonment_grace_rounds``, resolve their fate via the source-appropriate
    abandonment pool. N (``abandonment_grace_rounds``) is staff-tunable on
    ``SceneRoundDefaultsConfig``. A rescue (the bleed-out cleared before the window
    elapses) leaves no acute-peril instance, so ``resolve_abandonment`` naturally
    no-ops — rescue beats the check.
    """
    if not held_ids:
        return
    from world.scenes.models import get_scene_round_defaults_config  # noqa: PLC0415
    from world.vitals.peril_resolution import acute_peril_instances  # noqa: PLC0415
    from world.vitals.services import resolve_abandonment  # noqa: PLC0415

    grace = get_scene_round_defaults_config().abandonment_grace_rounds
    for p in scene_round.participants.filter(pk__in=held_ids).select_related(
        "character_sheet__character"
    ):
        sheet = p.character_sheet
        inst = acute_peril_instances(sheet).filter(abandoned_since_round__isnull=False).first()
        if inst is None:
            continue
        if scene_round.round_number - inst.abandoned_since_round >= grace:
            resolve_abandonment(sheet)


def resolve_solo_abandoned_victims(
    room: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    departing: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM
) -> None:
    """Solo-case abandonment (#1479 Task 8): a departure leaves a downed victim alone.

    When ``departing`` leaves ``room`` and that removes the LAST potential rescuer,
    any still-downed victim there (present, ``not can_act``, carrying an acute-peril
    condition) has their fate resolved IMMEDIATELY via the source-appropriate
    abandonment pool — no frozen limbo waiting for a round that will never come.

    Called from ``Room.at_object_leave``, which fires BEFORE the mover leaves the
    room's ``contents``; ``departing`` is therefore excluded from the rescuer check.
    A single cheap room-bound query short-circuits ordinary rooms (no acute peril
    present → no work).
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.vitals.peril_resolution import (  # noqa: PLC0415
        _acute_peril_condition_names,
        potential_rescuer_present,
    )
    from world.vitals.services import can_act, resolve_abandonment  # noqa: PLC0415

    sheets = _present_character_sheets(room)
    char_ids = [s.character_id for s in sheets]
    if not char_ids:
        return
    peril_ids = set(
        ConditionInstance.objects.filter(
            target_id__in=char_ids,
            condition__name__in=_acute_peril_condition_names(),
        ).values_list("target_id", flat=True)
    )
    if not peril_ids:
        return

    departing_id = departing.id if departing is not None else None
    for sheet in sheets:
        if sheet.character_id not in peril_ids:
            continue
        if sheet.character_id == departing_id or can_act(sheet):
            continue
        if potential_rescuer_present(sheet, room, exclude_character_id=departing_id):
            continue
        resolve_abandonment(sheet)


def maybe_finish_empty_scene(
    room: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    leaving: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM
) -> None:
    """Finish ``room``'s active scene if no PC other than ``leaving`` remains there.

    Mirrors ``resolve_solo_abandoned_victims``'s early-return and
    exclude-the-departing-id pattern (#1361). Called from ``Room.at_object_leave``
    (movement — fires before the mover actually leaves ``room.contents``, hence
    ``leaving``) and from ``Character.at_post_unpuppet`` (disconnect — called
    after Evennia's own base-class relocation has already removed the character
    from ``room.contents``, so ``leaving`` has no practical effect there but is
    passed for signature symmetry).
    """
    from world.battles.models import Battle  # noqa: PLC0415
    from world.scenes.models import Scene  # noqa: PLC0415
    from world.scenes.scene_admin_services import finish_scene_full  # noqa: PLC0415

    scene = Scene.objects.filter(location=room, is_active=True).first()
    if scene is None:
        return

    # #1361: a scene backing a live CombatEncounter/Battle has its own
    # lifecycle, resolved via combat/battle outcome rather than room emptiness
    # — auto-closing it here would be premature. These auxiliary scenes also
    # lack the account/participant setup a real RP scene has, so
    # finish_scene_full's broadcast step crashes on them (discovered via CI:
    # world.stories.tests.test_flee_services.FleeStoryCriticalNPCTests, whose
    # CombatEncounter fixture regressed against this function). The
    # combat/mission-disconnect-policy follow-up (#1899) decides what should
    # happen to a live encounter/battle on disconnect; this just leaves them
    # untouched for now.
    if scene.combat_encounters.filter(completed_at__isnull=True).exists():
        return
    if Battle.objects.filter(scene=scene, concluded_at__isnull=True).exists():
        return

    exclude_id = leaving.pk if leaving is not None else None
    for obj in room.contents:
        if obj.pk == exclude_id:
            continue
        try:
            obj.sheet_data  # noqa: B018 — attribute access guards NPC/prop skip
        except (AttributeError, ObjectDoesNotExist):
            continue
        return  # a PC remains — scene stays active

    finish_scene_full(scene)


@transaction.atomic
def resolve_scene_round(scene_round: SceneRound) -> SceneRound:
    """Unconditionally resolve a DECLARING round: execute declared CHALLENGE actions in
    initiative order, fire the shared END tick (which advances acute conditions — DoTs,
    bleed-out, plummet), delete the round's bridge rows, then either advance to the next
    round or auto-end.

    Auto-end: a ``start_reason==DANGER`` round ends (COMPLETED) once no ACTIVE participant
    still carries an acute danger condition (``_danger_persists`` — the peril has cleared).
    Any other round advances to the next round (DECLARING).

    Callers gate WHEN to resolve: ``maybe_resolve_scene_round`` resolves only once the
    presence-gated completion rule is met; a GM force-resolve calls this directly to resolve
    an incomplete round (undeclared present participants are swept as implicit passes)."""
    rnd = SceneRound.objects.select_for_update().get(pk=scene_round.pk)
    if rnd.status != RoundStatus.DECLARING:
        msg = f"Cannot resolve scene round: status is {rnd.status}, expected declaring."
        raise ValueError(msg)
    rnd.status = RoundStatus.RESOLVING
    rnd.save(update_fields=["status"])

    # Snapshot who declared this round BEFORE _resolve_scene_declarations deletes the
    # declaration rows. A present ``can_act`` participant who did NOT declare (swept as an
    # implicit pass by quorum completion) is excluded from the END-tick target set below:
    # their OWN acute conditions must not advance from a round they didn't engage in
    # (ADR-0004 — an AFK character is not harmed while away). Declared participants, absent
    # participants, and present-``not can_act`` participants (e.g. an unconscious victim)
    # tick as before.
    from world.vitals.services import can_act  # noqa: PLC0415

    declared_ids = set(
        rnd.action_declarations.filter(
            round_number=rnd.round_number, is_immediate=False
        ).values_list("participant_id", flat=True)
    )
    present_ids = {s.character_id for s in _present_character_sheets(rnd.room)}

    # Acute-peril narrowing (#1479): decide each DOWNED victim's fate BEFORE
    # _resolve_scene_declarations deletes this round's declaration rows, since the
    # hostile-driver check reads this round's declarations. A downed victim is a
    # present participant who cannot act yet carries an acute-peril condition (e.g.
    # Bleeding Out). Their peril advances on the END tick ONLY when a hostile party
    # drove this round; otherwise it HOLDS and we mark them abandoned (when a rescuer
    # is present). If a hostile drives again, the marker is cleared.
    downed_victim_ids, advancing_downed_ids = _resolve_downed_victim_peril(
        rnd, present_ids, declared_ids
    )

    # #1479 (plummet): a falling character's descent is ENVIRONMENTAL and
    # self-completing — it must advance every round regardless of who drove the
    # round, so it is exempt from the #1480 AFK own-peril skip below (and, via
    # _acute_peril_condition_names excluding PLUMMETING, from the downed-victim
    # hold/abandonment). Gravity does not pause for an idle round.
    plummeting_ids = _plummeting_character_ids(rnd)

    from world.scenes.succor_content import ensure_succor_challenges_for_round  # noqa: PLC0415

    ensure_succor_challenges_for_round(rnd)
    _resolve_scene_declarations(rnd)

    targets = []
    # Held-bleed-out+plummeting victims are excluded from the main tick (to keep their
    # bleed-out held) but must still have their plummet advanced this round.
    held_plummet_targets = []
    for p in rnd.participants.filter(status=SceneRoundParticipantStatus.ACTIVE).select_related(
        "character_sheet__character"
    ):
        sheet = p.character_sheet
        # #1480: a present, conscious, undeclared participant's OWN peril does not
        # advance from a round they didn't engage in (AFK own-peril skip) — UNLESS
        # they are plummeting, whose descent always advances (#1479).
        if (
            sheet.character_id in present_ids
            and can_act(sheet)
            and p.pk not in declared_ids
            and sheet.character_id not in plummeting_ids
        ):
            continue
        # #1479: a downed victim advances only when a hostile party drove the round.
        # Plummet exemption: gravity descends every round even when the bleed-out is
        # held — collect held+plummeting victims separately for a direct advance_plummet
        # call that does NOT also call advance_bleed_out (#1479 final-review).
        if p.pk in downed_victim_ids and p.pk not in advancing_downed_ids:
            if sheet.character_id in plummeting_ids:
                held_plummet_targets.append(sheet.character)
            continue
        targets.append(sheet.character)
    tick_round_for_targets(targets, timing="end")

    from world.scenes.sudden_harm import resolve_pending_interpose_harm  # noqa: PLC0415

    resolve_pending_interpose_harm(rnd)

    # Advance plummet for victims whose bleed-out is held but who are also falling.
    # They were excluded from the main tick above to keep their bleed-out held, but
    # gravity does not pause for an abandoned round — their descent must still advance
    # (#1479 final-review). advance_plummet is called directly (not tick_round_for_targets)
    # so advance_bleed_out is NOT triggered for these victims.
    if held_plummet_targets:
        from world.areas.positioning.plummet import advance_plummet  # noqa: PLC0415

        advance_plummet(held_plummet_targets)

    # #1479 Task 8: a held (abandoned, non-advancing) downed victim who has waited
    # out the abandonment grace window resolves via the source-appropriate
    # abandonment pool. Done before the auto-end check so a resolved peril lets a
    # DANGER round complete instead of freezing in limbo.
    _resolve_abandonment_grace(rnd, downed_victim_ids - advancing_downed_ids)

    rnd.status = RoundStatus.BETWEEN_ROUNDS
    rnd.save(update_fields=["status"])
    if rnd.start_reason == SceneRoundStartReason.DANGER and not _danger_persists(rnd):
        end_scene_round(rnd)  # peril cleared -> the danger round is done
    else:
        start_scene_round(rnd)  # -> DECLARING, round_number += 1
    scene_round.refresh_from_db()
    return scene_round


def maybe_resolve_scene_round(scene_round: SceneRound) -> SceneRound:
    """Resolve iff the presence-gated completion rule is met. No-op otherwise."""
    if scene_round.status == RoundStatus.DECLARING and scene_round_is_complete(scene_round):
        return resolve_scene_round(scene_round)
    return scene_round


@dataclass
class ChallengeResolutionRequest:
    """Pre-built resolution request for one declared challenge action.

    Callers construct these from their own declaration rows (ordered appropriately),
    then pass the list to :func:`resolve_challenge_declarations`.
    """

    character: ObjectDB
    challenge_instance: ChallengeInstance
    approach: ChallengeApproach
    actor_label: str


def resolve_challenge_declarations(
    requests: list[ChallengeResolutionRequest],
    *,
    broadcast: Callable[[str], None],
) -> list[ChallengeResolutionResult]:
    """Resolve a PRE-ORDERED list of declared challenge actions.

    For each request:

    1. Re-validate eligibility via ``get_available_actions`` — skip+log if no match.
    2. Call ``resolve_challenge``; skip if outcome is None.
    3. Render + broadcast the OUTCOME narration line when ``outcome.check_result`` is set.

    The caller is responsible for:
    - Ordering ``requests`` (initiative order, resolution_order, etc.).
    - Deleting bridge rows after this function returns.
    - Scoping the outer ``transaction.atomic`` block.

    Returns the list of non-None outcomes in resolution order.
    """
    from world.mechanics.challenge_resolution import resolve_challenge  # noqa: PLC0415
    from world.mechanics.services import get_available_actions  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        render_challenge_outcome_narration,
    )

    outcomes: list[ChallengeResolutionResult] = []
    for req in requests:
        location = req.challenge_instance.location
        available_actions = get_available_actions(req.character, location)
        matching = next(
            (
                a
                for a in available_actions
                if (
                    a.challenge_instance_id == req.challenge_instance.pk
                    and a.approach_id == req.approach.pk
                )
            ),
            None,
        )
        if matching is None:
            logger.warning(
                "Skipping deferred challenge declaration for character %s "
                "(challenge_instance=%s, approach=%s): no matching AvailableAction.",
                req.character.pk,
                req.challenge_instance.pk,
                req.approach.pk,
            )
            continue
        outcome = resolve_challenge(
            req.character, req.challenge_instance, req.approach, matching.capability_source
        )
        if outcome is None:
            continue
        outcomes.append(outcome)
        if outcome.check_result is not None:
            narration = render_challenge_outcome_narration(
                actor_label=req.actor_label,
                challenge_name=outcome.challenge_name,
                approach_name=outcome.approach_name,
                outcome_label=outcome.check_result.outcome_name,
                success_level=outcome.check_result.success_level,
            )
            broadcast(narration)
    return outcomes


def _resolve_scene_declarations(scene_round: SceneRound) -> None:
    """Resolve declared CHALLENGE actions for the round in initiative order, re-validating
    eligibility via get_available_actions (mirrors combat _resolve_declared_challenges),
    then delete the round's CHALLENGE bridge rows. Pass rows resolve to nothing.

    Succor declarations (``challenge_instance is None``; identified instead by
    ``succor_target``) and Interpose declarations (identified by ``interpose_target``,
    #1316) are excluded from both the generic challenge-resolution sweep and the delete
    below, for the same reason (#1744 bugfix, extended to Interpose): each is resolved
    reactively by a reader that runs AFTER this function — Succor by
    ``SceneRoundContext.get_cover_for`` (called from the END tick), which caches its
    graded outcome onto the declaration's ``succor_resolution`` field; Interpose by
    ``resolve_pending_interpose_harm``, which reads ``interpose_target`` fresh each time
    and caches nothing back onto the row (it resolves and deletes the bound
    ``PendingSuddenHarm`` instead). Deleting either declaration here would crash the
    generic sweep (which unconditionally dereferences ``challenge_instance.location``),
    and for Succor would additionally erase the cache before it can ever be read. They
    are naturally scoped by ``(scene_round, round_number, participant)`` — round_number
    advances every round, so a leftover row from a past round is simply never matched
    again by the current-round filter; no extra cleanup is needed.
    """
    from world.scenes.interaction_services import broadcast_scene_outcome  # noqa: PLC0415

    declarations = list(
        scene_round.action_declarations.filter(
            round_number=scene_round.round_number,
            is_pass=False,
            is_immediate=False,
            challenge_instance__isnull=False,
        )
        .select_related(
            "participant",
            "participant__character_sheet",
            "participant__character_sheet__character",
            "challenge_instance",
            "challenge_instance__location",
            "challenge_approach",
        )
        .order_by("participant__initiative_order", "declared_at", "pk")
    )
    requests = [
        ChallengeResolutionRequest(
            character=decl.participant.character_sheet.character,
            challenge_instance=decl.challenge_instance,
            approach=decl.challenge_approach,
            actor_label=decl.participant.character_sheet.character.db_key,
        )
        for decl in declarations
    ]
    resolve_challenge_declarations(
        requests,
        broadcast=lambda narration: broadcast_scene_outcome(
            scene_round=scene_round, narration=narration
        ),
    )
    scene_round.action_declarations.filter(round_number=scene_round.round_number).exclude(
        Q(succor_target__isnull=False) | Q(interpose_target__isnull=False)
    ).delete()
