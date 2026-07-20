"""Situation evaluator registry for per-vow situational perks (#2536, Task 2).

Every registered evaluator has signature ``(ctx: SituationContext) -> bool``,
registered under a ``Situation`` value via ``@register(Situation.X)``. Rules
(spec §1, enforced by convention here, not by the type system):

- Pure read — no writes, ever.
- At most one query, or a small fixed number of BATCHED queries when a
  single query cannot express the read (documented per-evaluator below);
  never a query inside a Python loop (repo-wide "no queries in loops" rule).
- Missing required context (``None`` field, absent resolution shape) ->
  ``False``. A combat-positioning evaluator simply never holds outside
  combat; a DB-state evaluator evaluates anywhere.

Import direction (ADR-0010): this module is part of ``world.covenants`` and
reaches into ``world.combat`` / ``world.conditions`` / ``world.magic`` /
``world.npc_services`` / ``world.scenes`` — always at FUNCTION level
(``# noqa: PLC0415``), never at module level, so those apps never import back.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from world.covenants.perks.constants import Situation
from world.covenants.perks.context import SituationContext

if TYPE_CHECKING:
    from world.combat.models import CombatParticipant, CombatRoundAction
    from world.conditions.models import ConditionInstance

SITUATION_EVALUATORS: dict[str, Callable[[SituationContext], bool]] = {}

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
) -> Callable[[Callable[[SituationContext], bool]], Callable[[SituationContext], bool]]:
    """Decorator registering an evaluator function under a ``Situation`` value."""

    def _decorator(
        func: Callable[[SituationContext], bool],
    ) -> Callable[[SituationContext], bool]:
        SITUATION_EVALUATORS[situation] = func
        return func

    return _decorator


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
def at_range(ctx: SituationContext) -> bool:
    """See ``_melee_state``. AT_RANGE holds when engaged but none are adjacent."""
    return _melee_state(ctx) is False


@register(Situation.IN_MELEE)
def in_melee(ctx: SituationContext) -> bool:
    """See ``_melee_state``. IN_MELEE holds when an engaged enemy shares position."""
    return _melee_state(ctx) is True


@register(Situation.SURROUNDED)
def surrounded(ctx: SituationContext) -> bool:
    """Subject has >= SURROUNDED_LOCK_THRESHOLD active EngagementLock rows.

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
    return count >= SURROUNDED_LOCK_THRESHOLD


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
def target_distracted(ctx: SituationContext) -> bool:
    """See ``_distraction_condition_instance``. False when ``target`` is None."""
    if ctx.target is None:
        return False
    return _distraction_condition_instance(ctx.target.character) is not None


@register(Situation.TARGET_SWAYED_BY_ALLY)
def target_swayed_by_ally(ctx: SituationContext) -> bool:
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
    read (no fresh query once the handler is warm).
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
def target_focused_elsewhere(ctx: SituationContext) -> bool:
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
    One query (see ``_target_declared_action``).
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
def ally_low_health(ctx: SituationContext) -> bool:
    """Any covenant-mate of the holder is below ALLY_LOW_HEALTH_FRACTION.

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

    for mate in mates:
        if mate.character_sheet_id not in mate_sheet_ids:
            continue
        try:
            vitals = mate.character_sheet.vitals
        except CharacterVitals.DoesNotExist:
            continue
        if vitals.health_percentage < ALLY_LOW_HEALTH_FRACTION:
            return True
    return False


@register(Situation.DURING_NEGOTIATION)
def during_negotiation(ctx: SituationContext) -> bool:
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
    location after the first lookup).
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
def target_favorably_disposed(ctx: SituationContext) -> bool:
    """Target's NPCStanding.affection toward holder is >= FAVORABLY_DISPOSED_MIN_AFFECTION.

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

    return NPCStanding.objects.filter(
        persona=holder_persona,
        npc_persona=target_persona,
        affection__gte=FAVORABLY_DISPOSED_MIN_AFFECTION,
    ).exists()
