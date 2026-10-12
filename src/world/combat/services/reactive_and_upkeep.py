"""Interpose dispatch, succor, round-start and reactive upkeep, break-bar records."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from actions.errors import ActionDispatchError
from flows.constants import EventName
from flows.events.payloads import CombatRoundStartingPayload, DamagePreApplyPayload
from world.combat import services as _svc
from world.combat.constants import (
    BREAK_NOVELTY_MULTIPLIER,
    ClashFlavor,
    ClashResolution,
    CombatManeuver,
    EngagementLockStatus,
    ParticipantStatus,
)
from world.combat.models import (
    BreakBarContribution,
    Clash,
    ClashContribution,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    EngagementLock,
)
from world.combat.services.combos import detect_available_combos
from world.combat.services.interpose_helpers import _ensure_interpose_challenges
from world.combat.types import ActionOutcome, AvailableCombo
from world.magic.models.soulfray import SoulfrayConfig
from world.magic.services.anima import deduct_anima
from world.mechanics.types import ChallengeResolutionResult

if TYPE_CHECKING:
    from datetime import datetime

    from evennia.objects.models import ObjectDB

    from world.conditions.models import ConditionInstance
    from world.magic.models.anima import CharacterAnima
    from world.mechanics.engagement import CharacterEngagement

logger = logging.getLogger(__name__)


def _grade_interpose_damage(
    pre_payload: DamagePreApplyPayload,
    success_level: int,
    *,
    interposer: object | None = None,
    force_clean: bool = False,
) -> bool:
    """Shared clean/partial/fail damage banding for BOTH interpose paths (#2207).

    Extracted from :func:`apply_interpose_outcome` (the mundane
    capability-reaction path) so :func:`_try_technique_interpose` (a technique
    guardian's own cast-check resolution) grades identically without
    duplicating the covenant-role-scaling partial-block math:

    - **clean block** (``force_clean`` or ``success_level > 0``): the blow is
      fully turned aside — ``pre_payload.amount = 0``.
    - **partial** (``success_level == 0``, not forced-clean): the interposer
      softens but does not stop the blow — ``pre_payload.amount //= 2``. An
      interposer engaged in a role with a ``combat_interpose`` scaling row
      scales this reduction by their COVENANT_ROLE thread level (#2022,
      #2529): the deeper the vow, the more damage the partial block absorbs.
    - **failure** (``success_level < 0``): the interpose fails — no change.

    ``force_clean`` lets a caller fold in a resolution-type override (the
    mundane path's ``ChallengeResolutionResult.resolution_type == DESTROY``)
    without leaking that concept into this shared helper's contract.

    Returns ``True`` when this graded as a clean block — the technique path
    uses this to gate BLINK ward relocation (clean success only).
    """
    is_clean_block = force_clean or success_level > 0

    if is_clean_block:
        pre_payload.amount = 0
        return True

    if success_level == 0:
        # #2022/#2529: covenant-role scaling — a deeper vow blocks more damage
        # on a partial block. The bonus reduces the remaining damage further.
        divisor = 2
        if interposer is not None:
            from world.covenants.services import (  # noqa: PLC0415
                covenant_role_action_scaling_bonus,
            )

            bonus = covenant_role_action_scaling_bonus(interposer, "combat_interpose")
            if bonus > 0:
                # Scale: partial block reduces to amount / (2 + bonus).
                # A bonus of 1.0 (a deep SHIELD vow) makes the divisor 3,
                # blocking 67% instead of 50%.
                divisor = int(2 + bonus)
        pre_payload.amount //= divisor
        return False

    # Failure (success_level < 0) — the blow continues at full damage.
    return False


def apply_interpose_outcome(
    pre_payload: DamagePreApplyPayload,
    result: ChallengeResolutionResult,
    *,
    interposer: object | None = None,
) -> None:
    """Map a graded interpose resolution onto *pre_payload*.

    Mirrors :func:`~world.areas.positioning.plummet.resolve_catch`'s graded
    branches but acts on the incoming damage amount rather than plummet state.
    Delegates the clean/partial/fail banding to :func:`_grade_interpose_damage`
    (shared with the technique-guardian path, #2207) — this wrapper's only job
    is converting a ``ChallengeResolutionResult`` into the ``(success_level,
    force_clean)`` pair that helper expects: ``resolution_type == DESTROY``
    forces a clean block even at ``success_level <= 0`` (a capability-authored
    instant stop).
    """
    from world.mechanics.constants import ResolutionType  # noqa: PLC0415

    check_result = result.check_result
    success_level = check_result.success_level if check_result is not None else 0
    force_clean = result.resolution_type == ResolutionType.DESTROY

    _grade_interpose_damage(
        pre_payload, success_level, interposer=interposer, force_clean=force_clean
    )


def dispatch_interpose(  # noqa: PLR0913 - select_best_check_rating extends existing signature
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    pre_payload: DamagePreApplyPayload,
    *,
    approach: str | None,
    extra_modifiers: int = 0,
    select_best_check_rating: bool = False,
) -> ChallengeResolutionResult | None:
    """Resolve *interposer*'s interpose attempt and apply the graded outcome.

    Thin wrapper over :func:`~world.mechanics.reactions.dispatch_capability_reaction`:
    looks up the active Interpose :class:`~world.mechanics.models.ChallengeInstance`
    bound to *protected*, resolves it through *interposer*'s capabilities, and
    calls :func:`apply_interpose_outcome` to mutate *pre_payload* in place.

    *select_best_check_rating* (#2207) opts into the best-of-check reaction-action
    selection (Reflexes vs. the Melee-Defense twin) when *approach* is ``None`` —
    passed ``True`` by :func:`_try_interpose` (the combat damage path). Default
    ``False`` preserves the plain first-match behavior for the scene-cover caller
    (``world.scenes.sudden_harm``), which passes ``approach=None`` unchanged.

    Returns the :class:`~world.mechanics.types.ChallengeResolutionResult`, or
    ``None`` when no active Interpose challenge is bound to *protected* or
    *interposer* has no qualifying approach.
    """
    import functools  # noqa: PLC0415

    from world.combat.interpose_content import INTERPOSE_CHALLENGE_NAME  # noqa: PLC0415
    from world.mechanics.reactions import dispatch_capability_reaction  # noqa: PLC0415

    return dispatch_capability_reaction(
        interposer,
        protected,
        challenge_name=INTERPOSE_CHALLENGE_NAME,
        approach=approach,
        error_msg=(
            f"No interpose approach is available to {interposer!r} "
            f"for protected target {protected!r}."
        ),
        outcome_fn=functools.partial(apply_interpose_outcome, pre_payload, interposer=interposer),
        select_best_check_rating=select_best_check_rating,
        extra_modifiers=extra_modifiers,
    )


def _ensure_succor_challenges(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Round pre-pass: bind a Succor ChallengeInstance to each protected ally.

    Mirrors _ensure_interpose_challenges but Succor always names a specific ally
    (no "any ally" path — see declare_succor's docstring).
    """
    from world.mechanics.models import ChallengeInstance, ChallengeTemplate  # noqa: PLC0415

    succor_actions = [
        action
        for action in pc_actions.values()
        if action.maneuver == CombatManeuver.SUCCOR and action.is_ready
    ]
    if not succor_actions:
        return

    from world.combat.succor_content import SUCCOR_CHALLENGE_NAME  # noqa: PLC0415

    try:
        template = ChallengeTemplate.objects.get(name=SUCCOR_CHALLENGE_NAME)
    except ChallengeTemplate.DoesNotExist:
        logger.warning(
            "Succor ChallengeTemplate not seeded; skipping challenge binding for encounter %s.",
            encounter.pk,
        )
        return

    room = encounter.room
    for action in succor_actions:
        ally_char = action.focused_ally_target.character_sheet.character
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=ally_char,
            is_active=True,
            defaults={"location": room, "is_revealed": True},
        )


def _ensure_reactive_challenges(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Round pre-pass: bind both Interpose and Succor challenge instances.

    A single call site for ``resolve_round`` (#1273, #1744) — keeps the two
    independent reactive-challenge binders (blow vs. hazard) from adding a
    second statement to an already-large function.
    """
    _ensure_interpose_challenges(encounter, pc_actions)
    _ensure_succor_challenges(encounter, pc_actions)


def dispatch_succor(
    succorer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    approach: str | None,
    extra_modifiers: int = 0,
) -> float:
    """Resolve *succorer*'s Succor attempt against *protected* and return the multiplier.

    Thin wrapper over dispatch_capability_reaction, mirroring dispatch_interpose.
    Returns 1.0 (no cover) when no active Succor challenge is bound to *protected*.
    """
    from world.combat.succor_content import SUCCOR_CHALLENGE_NAME  # noqa: PLC0415
    from world.mechanics.reactions import dispatch_capability_reaction  # noqa: PLC0415
    from world.mechanics.succor_shared import apply_succor_outcome  # noqa: PLC0415

    outcome = {"multiplier": 1.0}

    def _capture(result: ChallengeResolutionResult) -> None:
        outcome["multiplier"] = apply_succor_outcome(result)

    result = dispatch_capability_reaction(
        succorer,
        protected,
        challenge_name=SUCCOR_CHALLENGE_NAME,
        approach=approach,
        error_msg=(
            f"No succor approach is available to {succorer!r} for protected target {protected!r}."
        ),
        outcome_fn=_capture,
        extra_modifiers=extra_modifiers,
    )
    if result is None:
        return 1.0
    return outcome["multiplier"]


def _get_anima(character: ObjectDB) -> CharacterAnima | None:  # noqa: OBJECTDB_PARAM
    """Return the CharacterAnima row for *character*, or None if absent.

    Uses the ``anima`` reverse OneToOneField relation set by
    ``CharacterAnima.character`` (``related_name="anima"``). Mirrors the
    accessor used by ``CombatParticipant.available_strain``.

    Returns None when no CharacterAnima row exists (defensive; characters
    without an anima pool cannot sustain reactive conditions).
    """
    from world.magic.models.anima import CharacterAnima  # noqa: PLC0415

    try:
        return CharacterAnima.objects.get(character_id=character.pk)
    except CharacterAnima.DoesNotExist:
        return None


def active_combat_engagement_for(  # noqa: OBJECTDB_PARAM
    character: ObjectDB,
) -> CharacterEngagement | None:
    """The character's live COMBAT ``CharacterEngagement`` (``source`` is the encounter), or None.

    The reverse OneToOne accessor caches on the identity-mapped instance (no query on
    a warm path); a pk-less engagement is a row deleted through a queryset; a non-COMBAT
    engagement (challenge/mission stakes) is not combat. Extracted from
    ``ParticipantSerializer._combat_engagement`` (#3573) so reactive-cost seams can
    read ``engagement.source.is_lethal``.
    """
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    try:
        engagement = character.engagement
    except (AttributeError, CharacterEngagement.DoesNotExist):
        return None
    if engagement.pk is None or engagement.engagement_type != EngagementType.COMBAT:
        return None
    return engagement


def _fire_round_start(enc: CombatEncounter, round_number: int) -> list[AvailableCombo]:
    """Emit COMBAT_ROUND_STARTING, drain upkeep, detect combos.

    Called once at the top of ``resolve_round`` after the DECLARING→RESOLVING
    transition.  Bundles three sequential steps so the caller contributes a
    single statement toward the ``PLR0915`` limit.
    """
    _svc.emit_event(
        EventName.COMBAT_ROUND_STARTING,
        CombatRoundStartingPayload(
            encounter_id=enc.pk,
            round_number=round_number,
        ),
        location=enc.room,
    )
    drain_reactive_upkeep(enc)
    return detect_available_combos(enc, round_number)


def _narrate_upkeep_lapse(inst: ConditionInstance, encounter: CombatEncounter) -> None:
    """Tell the payer, the bearer (when different) and the room that a ward lapsed (#3574).

    Called immediately before the lapse ``inst.delete()`` so the names are
    still resolvable. The payer rule is ``drain_reactive_upkeep``'s own:
    ``source_character`` when set, else the bearer. Room line carries no
    numbers; the private lines say only that the fee could not be met.
    """
    from world.scenes.interaction_services import narrate_privately  # noqa: PLC0415

    bearer = inst.target
    payer = inst.source_character or bearer
    ward = inst.condition.name
    if payer.pk == bearer.pk:
        narrate_privately(payer, f"You cannot sustain {ward}; it lapses.")
    else:
        narrate_privately(payer, f"You cannot sustain {ward} on {bearer}; it lapses.")
        narrate_privately(bearer, f"{payer}'s {ward} over you lapses.")
    _svc._broadcast_commitment_line(encounter, f"The {ward} over {bearer} gutters out.")  # noqa: SLF001 (test patch seam)


def _debit_ally_paid_upkeep(
    inst: ConditionInstance, cost: int, *, encounter: CombatEncounter
) -> None:
    """Debit a condition's upkeep from its ally ``source_character`` payer.

    The payer is the condition's ``source_character`` — distinct from the
    bearer. If the payer cannot pay in full and hasn't consented, the
    condition lapses (its ``ConditionInstance`` row is deleted and any
    ``Trigger`` rows on it cascade). A consented payer instead runs into
    deficit and accrues Soulfray (#3573) via ``_pay_upkeep``.
    """
    payer = inst.source_character
    payer_anima = _get_anima(payer)
    if payer_anima is None:
        _narrate_upkeep_lapse(inst, encounter)
        inst.delete()  # lapse — Trigger rows cascade via source_condition FK
        return
    if payer_anima.current < cost and not inst.soulfray_consented:
        _narrate_upkeep_lapse(inst, encounter)
        inst.delete()  # lapse - Trigger rows cascade via source_condition FK
        return
    _pay_upkeep(payer, payer_anima, cost, inst, encounter)


def _pay_upkeep(
    payer: ObjectDB,  # noqa: OBJECTDB_PARAM
    anima: CharacterAnima,
    cost: int,
    inst: ConditionInstance,
    encounter: CombatEncounter,
) -> None:
    """Debit one round of upkeep; a consented payer runs into deficit and accrues (#3573).

    Shared by the ally-paid and self-paid upkeep branches of
    ``drain_reactive_upkeep`` so the debit-then-accrue sequencing lives in one
    place. Unconsented callers must not reach here already-unaffordable - the
    caller lapses the condition instead.
    """
    deficit = deduct_anima(payer, cost, lethal=encounter.is_lethal)
    if not inst.soulfray_consented:
        return
    _svc.accumulate_soulfray(
        character=payer,
        anima=anima,
        deficit=deficit,
        soulfray_config=SoulfrayConfig.objects.cached_singleton(),
        check_result=None,
        lethal=encounter.is_lethal,
    )
    if deficit > 0:
        _svc._broadcast_commitment_line(  # noqa: SLF001 (test patch seam)
            encounter, f"{payer} bleeds soul to keep the ward on {inst.target}."
        )


def _drain_participant_upkeep(
    part: CombatParticipant, anima: CharacterAnima, encounter: CombatEncounter
) -> None:
    """Debit one participant's sustained conditions for this round.

    Anima is written at most once (after the loop) so that N self-sustained
    conditions produce a single UPDATE rather than N; ally-sourced conditions
    debit their payer's pool immediately, since that payer is not necessarily
    among the participants being iterated. A consented instance that runs
    unaffordable (#3573) is the rare exception: it flushes the accumulated
    ``remaining`` first, then pays into deficit through ``_pay_upkeep`` rather
    than lapsing.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    char = part.character_sheet.character
    instances = ConditionInstance.objects.filter(
        target=char,
        is_suppressed=False,
        resolved_at__isnull=True,
        condition__upkeep_anima_per_round__gt=0,
    ).select_related("condition")
    remaining = anima.current
    for inst in instances:
        cost = inst.condition.upkeep_anima_per_round
        if inst.source_character_id and inst.source_character_id != char.id:
            _debit_ally_paid_upkeep(inst, cost, encounter=encounter)
            continue
        if remaining >= cost:
            remaining -= cost
        elif inst.soulfray_consented:
            anima.current = remaining
            anima.save(update_fields=["current"])
            _pay_upkeep(char, anima, cost, inst, encounter)
            # deduct_anima (inside _pay_upkeep) re-fetches CharacterAnima by
            # pk under select_for_update; SharedMemoryModel identity-maps by
            # pk so that call returns this same instance and its glut-first
            # spend already landed on anima.current - carry that forward
            # instead of clobbering it back to 0 (#3573 review fix).
            remaining = anima.current
        else:
            _narrate_upkeep_lapse(inst, encounter)
            inst.delete()  # lapse — Trigger rows cascade via source_condition FK
    if remaining != anima.current:
        anima.current = remaining
        anima.save(update_fields=["current"])


def drain_reactive_upkeep(encounter: CombatEncounter) -> None:
    """Debit per-round upkeep from each active participant's sustained conditions.

    For each ACTIVE participant, for each active (not suppressed, not resolved)
    condition with ``upkeep_anima_per_round > 0``: spend that anima from the
    condition's payer's ``CharacterAnima`` pool. If the payer cannot pay in
    full, the condition lapses — its ``ConditionInstance`` row is deleted and
    any ``Trigger`` rows on it cascade. The lapse is narrated to the payer, the
    bearer and the room (#3574, ``_narrate_upkeep_lapse``).

    Payer rule (#2208): ``source_character`` pays when set — an ally ward
    strains its caster, never its bearer. Self-cast wards are unchanged
    (source == bearer). Only looking up a separate ``CharacterAnima`` when
    ``source_character_id`` differs from the bearer's keeps the common
    self-ward path on the single-query-per-participant code path below.

    Participants without a ``CharacterAnima`` row are skipped entirely — including
    any caster-paid wards they bear (ADR-0118 edge: an anima-less bearer's ally
    ward gets free upkeep; acceptable because player characters always have an
    anima row).

    Anima is written at most once per participant (after the inner loop) so that
    a round with N self-sustained conditions produces a single UPDATE rather
    than N; ally-sourced conditions debit their payer's pool immediately since
    that payer is not necessarily among the participants being iterated. A
    consented instance that runs unaffordable (#3573) is the rare exception: it
    flushes the accumulated ``remaining`` immediately, then pays through
    ``_pay_upkeep`` into deficit rather than lapsing.
    """
    parts = CombatParticipant.objects.filter(
        encounter=encounter, status=ParticipantStatus.ACTIVE
    ).select_related("character_sheet__character")
    for part in parts:
        anima = _get_anima(part.character_sheet.character)
        if anima is None:
            continue
        _drain_participant_upkeep(part, anima, encounter)


def _block_if_participant_mid_audere_majora_crossing(encounter: CombatEncounter) -> None:
    """Hard, unconditional block (#1899): a round must never resolve while an
    active participant is mid-Audere-Majora-crossing, regardless of
    ``encounter.is_paused`` — that flag is a separate, softer disconnect-pause
    concern. Extracted to keep ``resolve_round`` under the statement-count lint.
    """
    from world.magic.audere_majora import (  # noqa: PLC0415
        any_character_mid_audere_majora_crossing,
    )

    active_sheets = [
        p.character_sheet
        for p in encounter.participants.filter(status=ParticipantStatus.ACTIVE).select_related(
            "character_sheet"
        )
    ]
    if any_character_mid_audere_majora_crossing(active_sheets):
        raise ActionDispatchError(ActionDispatchError.PARTICIPANT_MID_CROSSING)


def _outcome_damaged_boss(outcome: ActionOutcome, boss_pk: int) -> bool:
    """Return True if the outcome's damage results include damage to the given boss."""
    return any(
        hasattr(r, "opponent_id") and r.opponent_id == boss_pk for r in outcome.damage_results
    )


def _record_story_envoy_rescue(action: CombatRoundAction, protected: ObjectDB) -> None:
    """Persist a successful PC guardian rescue for an active story contract."""
    encounter = action.participant.encounter
    beat = encounter.story_beat
    if beat is None:
        return
    from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

    activation = get_open_activation(beat)
    if activation is None:
        return
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    protected_sheet = CharacterSheet.objects.filter(character_id=protected.pk).first()
    if protected_sheet is None:
        return
    from world.societies.causal_recognition import record_envoy_rescue  # noqa: PLC0415

    record_envoy_rescue(
        activation,
        action.participant.character_sheet,
        source_id=action.pk,
        source_action_id=action.pk,
        protected_sheet=protected_sheet,
    )


def _record_story_break_recognition(
    encounter: CombatEncounter, boss: CombatOpponent, round_number: int
) -> None:
    """Persist authored opening causes when this boss break reaches zero (#3914)."""
    beat = encounter.story_beat
    if beat is None:
        return
    from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

    activation = get_open_activation(beat)
    if activation is None:
        return
    from world.societies.causal_recognition import record_created_opening  # noqa: PLC0415

    rows = BreakBarContribution.objects.filter(
        opponent=boss,
        round_number=round_number,
        participant__isnull=False,
    ).select_related("participant__character_sheet")
    for row in rows:
        record_created_opening(
            activation,
            row.participant.character_sheet,
            source_id=row.pk,
            contribution_kind=row.kind,
        )


def _persist_break_bar_events(
    boss: CombatOpponent,
    round_number: int,
    events: list[tuple[str, int | None, int | None]],
) -> int:
    """Persist one ``BreakBarContribution`` row per event; return the diversity-unit total.

    1 unit per distinct (actor, kind) pair this round, doubled to
    ``BREAK_NOVELTY_MULTIPLIER`` for a (kind, effect_type) pair's first-ever
    appearance across the whole encounter (checked against rows persisted in
    prior rounds — never rows created within this same call).
    """
    existing_pairs = set(
        BreakBarContribution.objects.filter(opponent=boss).values_list("kind", "effect_type_id")
    )
    novel_pairs_seen: set[tuple[str, int | None]] = set()
    actor_kind_pairs: set[tuple[int | None, str]] = set()

    for kind, participant_id, effect_type_id in events:
        BreakBarContribution.objects.create(
            opponent=boss,
            participant_id=participant_id,
            round_number=round_number,
            kind=kind,
            effect_type_id=effect_type_id,
        )
        actor_kind_pairs.add((participant_id, kind))
        pair = (kind, effect_type_id)
        if pair not in existing_pairs:
            novel_pairs_seen.add(pair)

    base_units = len(actor_kind_pairs)
    bonus_units = len(novel_pairs_seen) * (BREAK_NOVELTY_MULTIPLIER - 1)
    return base_units + bonus_units


def _pc_lock_hold_contributors(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
) -> list[int | None]:
    """Participant PKs (or a lone ``None``) crediting a HOLD event per LOCK win this round.

    A LOCK-flavor Clash against *boss* that resolved PC_DECISIVE/PC_MARGINAL this
    round is a PC-side win. Contributors are the PCs with a ``ClashContribution``
    on that clash's resolving-round ``ClashRound`` — falling back to a single
    unattributed (``None``) entry when the clash resolved with no PC contribution
    row (e.g. a pure-abandonment-adjacent edge case).
    """
    won_locks = Clash.objects.filter(
        encounter=encounter,
        npc_opponent=boss,
        flavor=ClashFlavor.LOCK,
        resolved_round=round_number,
        resolution__in=(ClashResolution.PC_DECISIVE, ClashResolution.PC_MARGINAL),
    )
    contributor_ids: list[int | None] = []
    for clash in won_locks:
        character_ids = ClashContribution.objects.filter(
            clash_round__clash=clash,
            clash_round__round_number=round_number,
        ).values_list("character_id", flat=True)
        participant_ids = list(
            CombatParticipant.objects.filter(
                encounter=encounter,
                character_sheet_id__in=character_ids,
            ).values_list("pk", flat=True)
        )
        if participant_ids:
            contributor_ids.extend(participant_ids)
        else:
            contributor_ids.append(None)
    return contributor_ids


def _boss_new_debuff_events(
    boss: CombatOpponent,
    encounter: CombatEncounter,
    round_started_at: datetime | None,
) -> list[int | None]:
    """Participant PKs (or ``None``) crediting a DEBUFF event for *boss* this round."""
    if boss.objectdb_id is None or round_started_at is None:
        return []
    return [
        _participant_id_for_objectdb(encounter, inst.source_character_id)
        for inst in _new_behavior_altering_conditions(boss.objectdb_id, round_started_at)
    ]


def _newly_suppressed_lieutenants(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
    round_started_at: datetime | None,
) -> list[tuple[CombatOpponent, int | None]]:
    """Lieutenants reinforcing *boss* that became suppressed this round (#2642).

    Round-scoped to the two events with a clean "this round" signal: a new
    behavior-altering condition landing on the lieutenant's ObjectDB
    (``applied_at`` within this round's window), or a new ACTIVE
    ``EngagementLock`` pinning the lieutenant (``started_round == round_number``).
    Status/morale-driven suppression has no per-round timestamp in the schema
    and is not used as a SUPPRESSION trigger — a documented approximation
    (#2642); it still counts toward the lieutenant gate via ``_active_reinforcer_count``.
    """
    lieutenants = list(CombatOpponent.objects.filter(reinforces=boss))
    if not lieutenants:
        return []

    events: list[tuple[CombatOpponent, int | None]] = []
    for lieutenant in lieutenants:
        if lieutenant.objectdb_id is not None and round_started_at is not None:
            for inst in _new_behavior_altering_conditions(lieutenant.objectdb_id, round_started_at):
                participant_id = _participant_id_for_objectdb(encounter, inst.source_character_id)
                events.append((lieutenant, participant_id))
        new_lock = EngagementLock.objects.filter(
            opponent=lieutenant,
            status=EngagementLockStatus.ACTIVE,
            started_round=round_number,
        ).first()
        if new_lock is not None:
            events.append((lieutenant, new_lock.participant_id))
    return events


def _new_behavior_altering_conditions(objectdb_id: int, since: datetime) -> list[ConditionInstance]:
    """Behavior-altering ``ConditionInstance`` rows applied to *objectdb_id* since *since*."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return list(
        ConditionInstance.objects.filter(
            target_id=objectdb_id,
            condition__category__alters_behavior=True,
            applied_at__gte=since,
        ).select_related("condition")
    )


def _has_active_behavior_altering_condition(objectdb_id: int) -> bool:
    """True if *objectdb_id* currently carries an active behavior-altering condition.

    Mirrors ``CharacterSheet.in_control``'s canonical active-condition read
    (ADR-0024): not suppressed, or suppression has expired.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    not_suppressed = Q(is_suppressed=False)
    suppression_expired = Q(suppressed_until__isnull=False, suppressed_until__lt=timezone.now())
    return ConditionInstance.objects.filter(
        not_suppressed | suppression_expired,
        target_id=objectdb_id,
        condition__category__alters_behavior=True,
    ).exists()


def _participant_id_for_objectdb(encounter: CombatEncounter, objectdb_id: int | None) -> int | None:
    """Resolve an ObjectDB id to the ``CombatParticipant`` pk fielding it in *encounter*."""
    if objectdb_id is None:
        return None
    return (
        CombatParticipant.objects.filter(
            encounter=encounter, character_sheet__character_id=objectdb_id
        )
        .values_list("pk", flat=True)
        .first()
    )
