"""Situation evaluator registry for per-vow situational perks (#2536, Task 2;
parameterized #2623 Task 3).

Every registered evaluator has signature ``(ctx: SituationContext, params:
SituationParams) -> bool``, registered under a ``Situation`` value via
``@register(Situation.X)``. Rules (spec §1, enforced by convention here, not
by the type system):

- Pure read — no writes, ever.
- At most one query, or a small fixed number of BATCHED queries when a
  single query cannot express the read (documented per-evaluator below);
  never a query inside a Python loop (repo-wide "no queries in loops" rule).
- Missing required context (``None`` field, absent resolution shape) ->
  ``False``. A combat-positioning evaluator simply never holds outside
  combat; a DB-state evaluator evaluates anywhere.
- ``params`` (#2623 spec §2) carries the authored row's parameter columns —
  ``NO_PARAMS`` for every pre-#2623 row shape. A blank/``None`` field on
  ``params`` means "use this evaluator's documented module-constant default"
  UNLESS the situation's ``SITUATION_PARAM_SPECS`` entry marks the field
  required (``perks/constants.py``), in which case a blank value means the
  situation never holds — see ``attacker_affinity``'s required ``affinity``.
  Evaluators that read no params at all still accept the argument (signature
  uniformity across the registry) and simply ignore it.

Import direction (ADR-0010): this module is part of ``world.covenants`` and
reaches into ``world.combat`` / ``world.conditions`` / ``world.magic`` /
``world.npc_services`` / ``world.scenes`` — always at FUNCTION level
(``# noqa: PLC0415``), never at module level, so those apps never import back.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from world.covenants.perks.constants import Situation, SituationOriginSide
from world.covenants.perks.context import SituationContext, SituationParams

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter, CombatParticipant, CombatRoundAction
    from world.conditions.models import ConditionInstance
    from world.magic.models.aura import CharacterAura

SITUATION_EVALUATORS: dict[str, Callable[[SituationContext, SituationParams], bool]] = {}

# --- Module-tuned thresholds (spec §1's "document the threshold as a module
# constant" instruction) ---

#: SURROUNDED fires at >= this many active EngagementLock rows on the subject.
SURROUNDED_LOCK_THRESHOLD = 2

#: ALLY_LOW_HEALTH fires when a covenant-mate's health_percentage falls below
#: this fraction (mirrors vitals.constants.PERMANENT_WOUND_THRESHOLD = 0.50 —
#: the "Last Bulwark" rung-1 calibration from the spec's worked examples).
ALLY_LOW_HEALTH_FRACTION = 0.5

#: TARGET_FAVORABLY_DISPOSED fires at NPCStanding.affection >= this value.
#: Any positive standing counts as "favorable" — apply_social_disposition_delta
#: (world/npc_services/social_disposition.py) only ever writes positive deltas
#: today (_TIER_DELTA has no negative entries), so 1 is the natural floor.
FAVORABLY_DISPOSED_MIN_AFFECTION = 1


def register(
    situation: str,
) -> Callable[
    [Callable[[SituationContext, SituationParams], bool]],
    Callable[[SituationContext, SituationParams], bool],
]:
    """Decorator registering an evaluator function under a ``Situation`` value."""

    def _decorator(
        func: Callable[[SituationContext, SituationParams], bool],
    ) -> Callable[[SituationContext, SituationParams], bool]:
        SITUATION_EVALUATORS[situation] = func
        return func

    return _decorator


def _origin_side_matches(encounter: CombatEncounter, origin_side: str) -> bool:
    """Directed-origin gate (#2623 spec §3): blank = side-blind; a non-blank
    side with a NULL ``initiated_by_pc_side`` never holds (direction
    unprovable). v1 side model: the subject is always a PC, so PC side =
    "ours"."""
    if not origin_side:
        return True
    if encounter.initiated_by_pc_side is None:
        return False
    if origin_side == SituationOriginSide.OURS:
        return encounter.initiated_by_pc_side
    return not encounter.initiated_by_pc_side


def _resolution_participant(resolution: object | None) -> CombatParticipant | None:
    """Duck-read ``resolution.participant``, or None outside combat.

    ``SituationContext.resolution`` is deliberately typed loosely (``object |
    None`` — a ``CombatRoundContext`` in combat, a check-pipeline context
    otherwise, or ``None``; see the ``SituationContext`` docstring's "duck-
    read" convention) — there is no shared base class to type-narrow against.
    This is the SINGLE place every combat-positioning evaluator reads
    ``.participant`` off it, so one suppression covers every call site
    instead of repeating the raw ``getattr`` at each of them.
    """
    return getattr(resolution, "participant", None)  # noqa: GETATTR_LITERAL


def _melee_state(ctx: SituationContext) -> bool | None:
    """Shared read for AT_RANGE/IN_MELEE. Returns True (melee), False (range),
    or None (undetermined — no participant, unplaced, or no engaged enemy).

    Data source, verified: ``CombatParticipant.current_position``
    (``world/combat/models.py:1057``, a cached ``Position`` lookup via
    ``world.areas.positioning.services.position_of``), the subject's active
    ``EngagementLock`` rows (``world/combat/models.py:3011`` — the queryable
    "currently duelling me" relation; the position graph has no direct
    per-participant "who am I engaged with" edge of its own), and a single
    BATCHED ``ObjectPosition`` lookup (``world/areas/positioning/models.py:363``)
    for every locked opponent's position at once (never one query per lock —
    "no queries in loops"). Three total queries: current_position, the lock
    list, the batched opponent-position lookup.

    Caveat: ``EngagementLock.opponent`` FKs to ``CombatOpponent``, an
    NPC-only model (``world/combat/models.py:378``) — no PC-vs-PC
    ``EngagementLock`` row shape exists; PvP tracks engagement via the
    separate ``Clash``/``ClashContribution`` family instead. So AT_RANGE and
    IN_MELEE are silently NPC-opponent-only, matching how the combat
    engagement model works today.
    """
    participant = _resolution_participant(ctx.resolution)
    if participant is None:
        return None
    subject_position = participant.current_position
    if subject_position is None:
        return None

    from world.combat.constants import EngagementLockStatus  # noqa: PLC0415
    from world.combat.models import EngagementLock  # noqa: PLC0415

    opponent_objectdb_ids = list(
        EngagementLock.objects.filter(
            participant=participant,
            status=EngagementLockStatus.ACTIVE,
        ).values_list("opponent__objectdb_id", flat=True)
    )
    if not opponent_objectdb_ids:
        return None

    from world.areas.positioning.models import ObjectPosition  # noqa: PLC0415

    enemy_position_ids = set(
        ObjectPosition.objects.filter(objectdb_id__in=opponent_objectdb_ids).values_list(
            "position_id", flat=True
        )
    )
    return subject_position.pk in enemy_position_ids


@register(Situation.AT_RANGE)
def at_range(ctx: SituationContext, params: SituationParams) -> bool:  # noqa: ARG001
    """See ``_melee_state``. AT_RANGE holds when engaged but none are adjacent.

    Reads no params (absent from ``SITUATION_PARAM_SPECS``)."""
    return _melee_state(ctx) is False


@register(Situation.IN_MELEE)
def in_melee(ctx: SituationContext, params: SituationParams) -> bool:  # noqa: ARG001
    """See ``_melee_state``. IN_MELEE holds when an engaged enemy shares position.

    Reads no params (absent from ``SITUATION_PARAM_SPECS``)."""
    return _melee_state(ctx) is True


@register(Situation.SURROUNDED)
def surrounded(ctx: SituationContext, params: SituationParams) -> bool:
    """Subject has >= the authored (or ``SURROUNDED_LOCK_THRESHOLD`` default)
    count of active EngagementLock rows (#2623 spec §2: optional
    ``count_threshold`` param, ``SITUATION_PARAM_SPECS``).

    Data source, verified: ``EngagementLock`` (``world/combat/models.py:3011``),
    filtered on the subject's participant + ``status=ACTIVE``. Adjacency is
    approximated via lock count rather than the position graph — an
    EngagementLock IS the queryable "currently fighting me" relation and
    stays a single ``.count()`` query; the heavier position-graph batch that
    AT_RANGE/IN_MELEE already pay for is not duplicated here. One query.

    Caveat: like AT_RANGE/IN_MELEE (see ``_melee_state``), ``EngagementLock``
    only ever tracks PC-vs-NPC engagement (``.opponent`` FKs to the NPC-only
    ``CombatOpponent`` model) — PvP uses ``Clash`` instead. SURROUNDED is
    silently NPC-opponent-only, even though "surrounded" reads as a general
    term.
    """
    participant = _resolution_participant(ctx.resolution)
    if participant is None:
        return False

    from world.combat.constants import EngagementLockStatus  # noqa: PLC0415
    from world.combat.models import EngagementLock  # noqa: PLC0415

    count = EngagementLock.objects.filter(
        participant=participant,
        status=EngagementLockStatus.ACTIVE,
    ).count()
    threshold = (
        params.count_threshold if params.count_threshold is not None else SURROUNDED_LOCK_THRESHOLD
    )
    return count >= threshold


def _distraction_condition_instance(target_character: object) -> ConditionInstance | None:
    """Shared lookup for TARGET_DISTRACTED / TARGET_SWAYED_BY_ALLY.

    Data source, verified: ``ConditionInstance.source_technique``
    (``world/conditions/models.py:1238``) + ``TechniqueFunctionTag``
    (``world/magic/models/techniques.py:609`` — "the SHARED vocabulary both
    per-vow specialties (#2443) and situational perks (#2536) target",
    ``world/magic/constants.py:20``). An active (``resolved_at`` null)
    condition on *target_character* whose applying technique carries the
    DISTRACTION or CHARM ``TechniqueFunction`` tag. One query. ``.distinct()``
    guards against the M2M-shaped join (``function_tags``) returning
    duplicate ``ConditionInstance`` rows when a technique carries both tags.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.magic.constants import TechniqueFunction  # noqa: PLC0415

    return (
        ConditionInstance.objects.filter(
            target=target_character,
            resolved_at__isnull=True,
            source_technique__function_tags__function__in=[
                TechniqueFunction.DISTRACTION,
                TechniqueFunction.CHARM,
            ],
        )
        .select_related("source_character")
        .distinct()
        .first()
    )


@register(Situation.TARGET_DISTRACTED)
def target_distracted(ctx: SituationContext, params: SituationParams) -> bool:  # noqa: ARG001
    """See ``_distraction_condition_instance``. False when ``target`` is None.

    Reads no params (absent from ``SITUATION_PARAM_SPECS``)."""
    if ctx.target is None:
        return False
    return _distraction_condition_instance(ctx.target.character) is not None


@register(Situation.TARGET_SWAYED_BY_ALLY)
def target_swayed_by_ally(ctx: SituationContext, params: SituationParams) -> bool:  # noqa: ARG001
    """Same condition as TARGET_DISTRACTED, applied by holder or a covenant-mate.

    Deliberately reads HISTORY via ``shares_covenant_with`` (ACTIVE membership
    only), NOT the membership+co-presence "covenant-mate" rule
    ``perks.services`` uses for beneficiary group membership — see that
    module's docstring ("What counts as a covenant-mate") for why the two
    questions differ.

    Data source, verified: ``ConditionInstance.source_character``
    (``world/conditions/models.py:1230`` — "Character who applied this
    condition", an ``ObjectDB`` FK) + ``Character.shares_covenant_with``
    (``typeclasses/characters.py:247`` — reads the cached covenant-role
    handler, "used by the reactive-filter ``shares_covenant`` op"). One query
    for the condition instance; ``shares_covenant_with`` is a cached-handler
    read (no fresh query once the handler is warm). Reads no params (absent
    from ``SITUATION_PARAM_SPECS``).
    """
    if ctx.holder is None or ctx.target is None:
        return False
    instance = _distraction_condition_instance(ctx.target.character)
    if instance is None or instance.source_character is None:
        return False
    applier = instance.source_character
    holder_character = ctx.holder.character
    if applier == holder_character:
        return True
    return bool(applier.shares_covenant_with(holder_character))


def _target_declared_action(ctx: SituationContext) -> CombatRoundAction | None:
    """Resolve the target's declared ``CombatRoundAction`` this round, or None.

    Split out of ``target_focused_elsewhere`` purely to keep that function's
    branch count under the repo's return-statement lint threshold — same
    single query described there.
    """
    if ctx.target is None or ctx.subject is None:
        return None
    participant = _resolution_participant(ctx.resolution)
    encounter_id = participant.encounter_id if participant is not None else None
    if encounter_id is None:
        return None

    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatParticipant, CombatRoundAction  # noqa: PLC0415

    target_participant = (
        CombatParticipant.objects.filter(
            character_sheet=ctx.target,
            encounter_id=encounter_id,
            status=ParticipantStatus.ACTIVE,
        )
        .select_related("encounter")
        .first()
    )
    if target_participant is None:
        return None

    return (
        CombatRoundAction.objects.filter(
            participant=target_participant,
            round_number=target_participant.encounter.round_number,
        )
        .select_related("focused_ally_target__character_sheet")
        .first()
    )


@register(Situation.TARGET_FOCUSED_ELSEWHERE)
def target_focused_elsewhere(
    ctx: SituationContext,
    params: SituationParams,  # noqa: ARG001
) -> bool:
    """Target's declared CombatRoundAction this round targets someone != subject.

    Data source, verified: ``CombatRoundAction.focused_opponent_target`` /
    ``.focused_ally_target`` (``world/combat/models.py:1073`` — "A PC's
    declared actions for a round"; only PC/sheet-backed combatants have a
    ``CombatParticipant`` row, matching ``ctx.target: CharacterSheet``). Only
    meaningful when the target is a PC/sheet-backed participant in the same
    encounter as the subject's resolution — an NPC-only opponent (no
    CharacterSheet) can never populate ``ctx.target`` in the first place, so
    this correctly reads False for that case rather than needing a special
    branch. ``focused_opponent_target`` is an NPC (never the subject, since
    ``subject`` is always a PC) so its presence alone means "elsewhere"; a
    ``focused_ally_target`` must be compared against the subject directly.
    One query (see ``_target_declared_action``). Reads no params (absent from
    ``SITUATION_PARAM_SPECS``).
    """
    action = _target_declared_action(ctx)
    if action is None:
        return False
    if action.focused_opponent_target_id is not None:
        return True
    if action.focused_ally_target_id is not None:
        return action.focused_ally_target.character_sheet_id != ctx.subject.pk
    return False


@register(Situation.ALLY_LOW_HEALTH)
def ally_low_health(ctx: SituationContext, params: SituationParams) -> bool:
    """Any covenant-mate of the holder is below the authored (or
    ``ALLY_LOW_HEALTH_FRACTION`` default) health fraction (#2623 spec §2:
    optional ``threshold_percent`` param — an authored percent, e.g. 25 means
    "below 25% health," converted to the same 0-1 fraction scale
    ``health_percentage`` uses).

    "Ally" scoping rule (Tehom's 2026-07-20 reversal of #2536's slice-1
    ruling): a candidate mate counts if they hold a non-departed
    (``CharacterCovenantRole.left_at__isnull=True``,
    ``world/covenants/models.py:649``) role in a covenant the HOLDER is also
    actively engaged in AND are co-present in the same encounter roster
    (below) — the mate's OWN ``engaged`` flag is irrelevant. A KO'd or
    disengaged covenant-mate still in the fight keeps counting toward this
    situation — Last Bulwark-style perks must fire hardest exactly when mates
    are going down, not stop firing the moment they do (no death-spiral). This
    matches ``services._ally_candidates``'s group definition, which this
    function deliberately mirrors. Leaving the encounter (FLED/REMOVED) still
    drops a mate — that's the co-presence half of the roster query below, not
    the covenant-membership query, and is unchanged by this reversal.

    Data source, verified: ``CharacterVitals.health_percentage``
    (``world/vitals/models.py:100``) for every ACTIVE ``CombatParticipant`` in
    the subject's resolution encounter (the only queryable roster available
    off ``resolution``). Membership is resolved with a FIXED number of
    queries regardless of roster size (never a query inside a Python loop —
    "no queries in loops"): one roster query (``select_related`` to avoid
    N+1 on vitals), one cached-handler read of the holder's active covenant
    ids (``Character.active_covenant_ids()`` — no query once the handler is
    warm), and one single BATCHED ``CharacterCovenantRole`` query across
    every candidate mate's ``character_sheet`` (filtered to the holder's
    covenant ids + non-departed) to build the mate set, compared in Python
    against each mate's health. Three queries total, fixed.
    """
    participant = _resolution_participant(ctx.resolution)
    if participant is None or ctx.holder is None:
        return False
    holder_character = ctx.holder.character
    if holder_character is None:
        return False

    holder_covenant_ids = holder_character.active_covenant_ids()
    if not holder_covenant_ids:
        return False

    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatParticipant as _CombatParticipant  # noqa: PLC0415
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    mates = list(
        _CombatParticipant.objects.filter(
            encounter_id=participant.encounter_id,
            status=ParticipantStatus.ACTIVE,
        )
        .exclude(character_sheet=ctx.holder)
        .select_related("character_sheet__vitals")
    )

    mate_sheet_ids = set(
        CharacterCovenantRole.objects.filter(
            character_sheet_id__in=[m.character_sheet_id for m in mates],
            covenant_id__in=holder_covenant_ids,
            left_at__isnull=True,
        ).values_list("character_sheet_id", flat=True)
    )
    if not mate_sheet_ids:
        return False

    fraction = (
        params.threshold_percent / 100
        if params.threshold_percent is not None
        else ALLY_LOW_HEALTH_FRACTION
    )
    for mate in mates:
        if mate.character_sheet_id not in mate_sheet_ids:
            continue
        try:
            vitals = mate.character_sheet.vitals
        except CharacterVitals.DoesNotExist:
            continue
        if vitals.health_percentage < fraction:
            return True
    return False


@register(Situation.DURING_NEGOTIATION)
def during_negotiation(ctx: SituationContext, params: SituationParams) -> bool:  # noqa: ARG001
    """Subject is in an active Scene and NOT resolving via a combat context.

    Simplest honest version per the plan (no dedicated social/parley scene
    marker exists yet): a subject currently inside a ``CombatRoundContext``
    (``resolution.participant`` present) is never "negotiating"; otherwise,
    an active room-scoped RP ``Scene`` at the subject's location — via
    ``get_active_scene`` (``world/scenes/interaction_services.py:38``) —
    counts as a negotiation/social context. ``get_active_scene`` already
    excludes Battle-backed scenes on its own, but that alone would NOT
    exclude an ordinary ``CombatEncounter``'s backing Scene (a
    ``CombatEncounter`` is not a ``Battle``) — the explicit
    ``resolution.participant`` check above is what actually guards against a
    false positive during real PC/NPC combat. One query (cached on the
    location after the first lookup). Reads no params (absent from
    ``SITUATION_PARAM_SPECS``).
    """
    if ctx.subject is None:
        return False
    if _resolution_participant(ctx.resolution) is not None:
        return False

    character = ctx.subject.character
    if character is None:
        return False

    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    return get_active_scene(character.location) is not None


@register(Situation.TARGET_FAVORABLY_DISPOSED)
def target_favorably_disposed(ctx: SituationContext, params: SituationParams) -> bool:
    """Target's NPCStanding.affection toward holder is >= the authored (or
    ``FAVORABLY_DISPOSED_MIN_AFFECTION`` default) minimum (#2623 spec §2:
    optional ``count_threshold`` param, ``SITUATION_PARAM_SPECS``).

    Data source, verified: ``NPCStanding`` (``world/npc_services/models.py:44``
    — "Per-(PC persona, NPC persona) durable disposition"), the exact ledger
    ``apply_social_disposition_delta`` (``world/npc_services/social_disposition.py``)
    mutates on a landed charm/flirt/social success — matching the spec's
    "favorable from a landed charm/flirt/social success" wording verbatim.
    Scoped to ``persona=holder's persona, npc_persona=target's persona``; a
    PC target (no matching row can exist by construction) correctly reads
    False rather than needing a special case. One query (plus persona
    resolution, itself a cached FK read via ``CharacterSheet.primary_persona``).
    """
    if ctx.holder is None or ctx.target is None:
        return False

    from world.npc_services.models import NPCStanding  # noqa: PLC0415
    from world.scenes.services import (  # noqa: PLC0415
        MissingPrimaryPersonaError,
        persona_for_character,
    )

    try:
        holder_persona = persona_for_character(ctx.holder.character)
        target_persona = persona_for_character(ctx.target.character)
    except MissingPrimaryPersonaError:
        return False

    minimum = (
        params.count_threshold
        if params.count_threshold is not None
        else FAVORABLY_DISPOSED_MIN_AFFECTION
    )
    return NPCStanding.objects.filter(
        persona=holder_persona,
        npc_persona=target_persona,
        affection__gte=minimum,
    ).exists()


@register(Situation.CHAMPION_DUEL)
def champion_duel(ctx: SituationContext, params: SituationParams) -> bool:  # noqa: ARG001
    """True when the SUBJECT is a participant in a Champion-duel combat encounter.

    ``is_champion_duel`` (#2536 slice 3) is stamped exclusively by
    ``world.battles.services.open_champion_duel`` on the ``CombatEncounter`` it
    creates — every other DUEL creation path, including the siege-engine
    skirmish opened by ``open_siege_engine_encounter`` (shares the same
    ``create_lethal_duel`` helper, no Champion-role requirement), leaves the
    flag False. Combat checks/casts already thread ``resolution`` (a
    ``CombatRoundContext``) into every ``SituationContext``, so no new
    threading is needed for this situation — one cached FK read
    (``participant.encounter``, idmapper-cached) and False outside combat.
    Reads no params (absent from ``SITUATION_PARAM_SPECS``).
    """
    participant = _resolution_participant(ctx.resolution)
    if participant is None:
        return False
    return participant.encounter.is_champion_duel is True


@register(Situation.ON_CHOSEN_GROUND)
def on_chosen_ground(ctx: SituationContext, params: SituationParams) -> bool:  # noqa: ARG001
    """True when the SUBJECT is a participant in an encounter stamped chosen-ground.

    ``on_chosen_ground`` (#2646) is stamped exclusively at encounter-CREATE time by
    ``world.combat.chosen_ground.compute_on_chosen_ground``, called from the three
    PC-vs-NPC encounter-creation seams (``world.combat.cast_seed.
    seed_or_feed_encounter_from_cast``, ``world.combat.duels.create_lethal_duel``,
    ``world.battles.services.open_place_encounter``) — every other DUEL creation
    path (``world.combat.duels.create_pvp_duel``) leaves it False. Mirrors
    ``champion_duel``'s shape exactly: one cached FK read (``participant.encounter``,
    idmapper-cached) and False outside combat. Reads no params (absent from
    ``SITUATION_PARAM_SPECS``).
    """
    participant = _resolution_participant(ctx.resolution)
    if participant is None:
        return False
    return participant.encounter.on_chosen_ground is True


@register(Situation.COMBAT_OPENED_FROM_PARLEY)
def combat_opened_from_parley(ctx: SituationContext, params: SituationParams) -> bool:
    """True for every combat resolution in an encounter that opened as a parley,
    gated by the optional directed ``origin_side`` param (#2623 spec §3 — blank
    = side-blind, today's behavior; ``ours``/``theirs`` requires
    ``CombatEncounter.initiated_by_pc_side`` to match, and NULL never holds a
    directed side — see ``_origin_side_matches``).

    ``opened_from_parley`` (#2536 slice 3, Task 4) is stamped exclusively by
    ``world.combat.cast_seed.seed_or_feed_encounter_from_cast`` when it CREATES a
    new encounter from a hostile cast landing inside an active, non-Battle-backed
    Scene (the same classification ``during_negotiation`` above documents) —
    feeding an existing encounter never flips the flag. v1 approximation (PR-body
    judgment call): the flag holds for the encounter's ENTIRE lifetime, not just
    its opening moment — "this fight started as a conversation that turned
    hostile" stays true throughout. One cached FK read (``participant.encounter``,
    idmapper-cached) and False outside combat; the origin-side gate reads an
    already-loaded field, no extra query.
    """
    participant = _resolution_participant(ctx.resolution)
    if participant is None:
        return False
    encounter = participant.encounter
    if not encounter.opened_from_parley:
        return False
    return _origin_side_matches(encounter, params.origin_side)


@register(Situation.AMBUSH_UNDERWAY)
def ambush_underway(ctx: SituationContext, params: SituationParams) -> bool:
    """True only during ROUND 1 of an encounter that opened as a surprise,
    gated by the optional directed ``origin_side`` param (#2623 spec §3 — same
    gate ``combat_opened_from_parley`` documents, see ``_origin_side_matches``).

    v1 semantics (documented approximation, #2536 slice 3 Task 4): holds when
    the encounter's CURRENT round (``CombatEncounter.round_number``, the
    ``AbstractRound`` scalar shared with ``SceneRound``) is 1 AND either
    ``opened_from_parley`` is True (a parley that turned hostile IS a surprise
    — nobody was braced for combat) OR at least one ``CombatRoundAction`` in
    round 1 has ``from_entrance=True`` (a dramatic technique-entrance opener,
    #2183). False from round 2 on — the ambush window closes once a full round
    has passed, regardless of how the fight opened. Data source, verified:
    ``CombatRoundAction.from_entrance`` (``world/combat/models.py:1095``),
    filtered to the SUBJECT's encounter (not just their own actions — an
    ambush is a property of the encounter, any entrance-cast participant
    counts) + ``round_number=1``. Two queries at most: the cached
    ``participant.encounter`` FK read, plus (only when ``opened_from_parley``
    is False) a single ``CombatRoundAction.objects.filter(...).exists()``
    lookup — never a query inside a loop. False outside combat; the
    origin-side gate reads an already-loaded field, no extra query.
    """
    participant = _resolution_participant(ctx.resolution)
    if participant is None:
        return False
    encounter = participant.encounter
    if encounter.round_number != 1:
        return False

    surprised = encounter.opened_from_parley
    if not surprised:
        from world.combat.models import CombatRoundAction  # noqa: PLC0415

        surprised = CombatRoundAction.objects.filter(
            participant__encounter_id=encounter.pk,
            round_number=1,
            from_entrance=True,
        ).exists()
    if not surprised:
        return False

    return _origin_side_matches(encounter, params.origin_side)


@register(Situation.ALLY_INTERCEPTED_FOR_ME)
def ally_intercepted_for_me(ctx: SituationContext, params: SituationParams) -> bool:  # noqa: ARG001
    """A covenant-mate of the holder has an armed INTERPOSE guarding the subject.

    Ratified v1 judgment call (#2536 slice 3, Task 5): DECLARED-guard
    semantics — holds as soon as a covenant-mate's INTERPOSE declaration is
    armed (``is_ready=True``) this round, whether or not the interpose ever
    actually intercepts damage. "The guarded moment is the situation" — a
    perk keying off this fires the instant cover is committed, not later when
    it resolves.

    "Mate" scoping mirrors ``ally_low_health`` exactly (see that function's
    docstring, "Ally scoping rule"): a candidate counts if they hold a
    non-departed (``CharacterCovenantRole.left_at__isnull=True``) role in a
    covenant the HOLDER is also actively engaged in — the mate's own
    ``engaged``/participant status beyond being co-present is irrelevant,
    same reversal (Tehom 2026-07-20). The SUBJECT themself is excluded from
    the interpose-declaration pool (a character can never be their own
    intercepting ally — a subject's own guard-anyone INTERPOSE must not
    self-satisfy this situation).

    Data source, verified: ``CombatRoundAction`` (``world/combat/models.py``
    ~1094-1140) filtered to the SUBJECT's encounter (``ctx.resolution`` is
    always the SUBJECT's resolution — see ``SituationContext`` docstring) +
    the encounter's current ``round_number`` (the same ``AbstractRound``
    scalar ``ambush_underway`` reads) + ``maneuver=CombatManeuver.INTERPOSE``
    + ``is_ready=True``, restricted to ACTIVE participants. A declaration
    "guards" the subject when its ``focused_ally_target_id`` is either the
    subject's own participant id (a specific-ally guard) or ``None``
    (guard-anyone, ``declare_interpose`` — ``world/combat/services.py:1846``
    — allows either). Query budget: one declarations query (as above,
    ``select_related`` the interposer's character sheet) + one BATCHED
    ``CharacterCovenantRole`` membership query across every guarding
    interposer's sheet id (never one query per candidate — "no queries in
    loops"). Two queries total, fixed regardless of interposer count. False
    outside combat. Reads no params (absent from ``SITUATION_PARAM_SPECS``).
    """
    participant = _resolution_participant(ctx.resolution)
    if participant is None or ctx.holder is None:
        return False
    holder_character = ctx.holder.character
    if holder_character is None:
        return False

    holder_covenant_ids = holder_character.active_covenant_ids()
    if not holder_covenant_ids:
        return False

    from world.combat.constants import CombatManeuver, ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatRoundAction  # noqa: PLC0415
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    encounter = participant.encounter
    declarations = list(
        CombatRoundAction.objects.filter(
            participant__encounter_id=encounter.pk,
            participant__status=ParticipantStatus.ACTIVE,
            round_number=encounter.round_number,
            maneuver=CombatManeuver.INTERPOSE,
            is_ready=True,
        )
        .exclude(participant_id=participant.pk)
        .select_related("participant__character_sheet")
    )
    if not declarations:
        return False

    guarding = [
        declaration
        for declaration in declarations
        if declaration.focused_ally_target_id is None
        or declaration.focused_ally_target_id == participant.pk
    ]
    if not guarding:
        return False

    mate_sheet_ids = set(
        CharacterCovenantRole.objects.filter(
            character_sheet_id__in=[d.participant.character_sheet_id for d in guarding],
            covenant_id__in=holder_covenant_ids,
            left_at__isnull=True,
        ).values_list("character_sheet_id", flat=True)
    )
    return any(d.participant.character_sheet_id in mate_sheet_ids for d in guarding)


def _attacker_aura(attacker: object) -> CharacterAura | None:
    """Reachable ``CharacterAura`` for ``attacker`` — ``attacker.objectdb.aura`` for
    a ``CombatOpponent`` (``objectdb`` nullable), else ``attacker.aura`` for a bare
    ObjectDB attacker. ``None`` on any missing relation; never raises. Split out of
    ``attacker_affinity`` to keep that function's return-statement count under the
    repo's lint threshold.
    """
    try:
        objectdb = attacker.objectdb
    except AttributeError:
        # Not a CombatOpponent (no `.objectdb` indirection) — treat the
        # attacker itself as the ObjectDB to read `.aura` off directly.
        objectdb = attacker
    if objectdb is None:
        return None

    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return objectdb.aura
    except (ObjectDoesNotExist, AttributeError):
        return None


@register(Situation.ATTACKER_AFFINITY)
def attacker_affinity(ctx: SituationContext, params: SituationParams) -> bool:
    """True when ``ctx.attacker`` is typed to ``params.affinity``, the required
    authored axis (#2536 slice 3 Task 6; renamed + parameterized #2623 spec §2 —
    required ``affinity``, optional ``threshold_percent``, ``SITUATION_PARAM_SPECS``).
    ``affinity`` is REQUIRED — ``NO_PARAMS`` (blank ``affinity``) never holds,
    regardless of what data the attacker carries.

    ``ctx.attacker`` is populated ONLY on a defense-side resolution (see
    ``SituationContext``'s docstring, "attacker") — a ``CombatOpponent`` or an
    ObjectDB-backed attacker; ``None`` on every offense-side resolution, which
    this evaluator reads as False. Resolution order, never raising on missing
    relations:

    1. A ``CombatOpponent`` with a non-empty AUTHORED ``affinity``
       (``world/combat/models.py`` — #2536 slice 3 field, for non-persona/
       generic NPCs that carry no ``CharacterAura`` row to infer from) —
       compared directly against ``params.affinity``. Authored typing wins
       outright when present (``threshold_percent`` is IGNORED on this path —
       an authored type is definitional, not a percentage); the aura
       fallback below is never consulted.
    2. A reachable ``ObjectDB`` carrying a ``CharacterAura``
       (``world/magic/models/aura.py`` — a ``OneToOneField`` with
       ``related_name="aura"``) — read via ``attacker.objectdb.aura`` for a
       ``CombatOpponent`` (``objectdb`` is nullable — covers persona-backed
       story NPCs AND PvP attackers, see the PvP note below) or
       ``attacker.aura`` for a bare ``ObjectDB`` attacker. With
       ``params.threshold_percent`` set, holds when ``params.affinity``'s own
       axis percentage is >= the threshold; unset, holds when
       ``dominant_affinity == params.affinity``.
    3. Otherwise False — no attacker, no authored affinity, and no aura data
       reachable (an ephemeral/generic NPC with neither).

    PvP note (v1 scope): a PvP attacker is a ``CombatOpponent`` row with
    ``objectdb`` set to the attacking PC (never an authored ``affinity`` —
    that field is generic-NPC-only), so path (2) is what covers PvP.
    ``world.combat.services.resolve_npc_attack`` is the ONLY defense-check
    site threaded with ``ctx.attacker`` in v1 — the penetration-vs-ward PvP
    path has no defender roll to thread this into.

    At most one query (the ``CharacterAura`` OneToOne fetch, reached only
    when no authored affinity short-circuits path 1 first).
    """
    if not params.affinity:
        return False
    attacker = ctx.attacker
    if attacker is None:
        return False

    from world.magic.types.aura import AffinityType  # noqa: PLC0415

    try:
        affinity = attacker.affinity
    except AttributeError:
        affinity = ""
    if affinity:
        return affinity == params.affinity

    aura = _attacker_aura(attacker)
    if aura is None:
        return False
    if params.threshold_percent is not None:
        axis_value = {
            AffinityType.CELESTIAL: aura.celestial,
            AffinityType.PRIMAL: aura.primal,
            AffinityType.ABYSSAL: aura.abyssal,
        }.get(params.affinity)
        # ``.get()`` (not ``[...]``) — a non-choice affinity string bypassing
        # full_clean (e.g. a row authored directly in the DB) yields None
        # here rather than a KeyError; never raise, just miss.
        return axis_value is not None and axis_value >= params.threshold_percent
    return aura.dominant_affinity == params.affinity
