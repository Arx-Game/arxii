"""Battle round resolution engine.

Iterates all unresolved BattleActionDeclarations for a round, casts each
declaration's technique once via ``resolve_battle_technique``, then routes
the result:

- ``success_level > 0`` → STRIKE: attrite the target unit + award VP to the
  participant's side; SUPPORT: award SUPPORT_VP.
- ``success_level <= 0`` → debit PC health then call
  ``process_damage_consequences`` (non-progressive, SQLite-safe).

The ``BattleRoundResult`` dataclass carries per-side VP totals, routed/
destroyed unit lists, and a casualty list for the caller to display or log.

This module also provides ``BattleTechniqueResolver`` and
``resolve_battle_technique``, which cast a declaration's ``technique`` through
the real magic envelope (``use_technique``). Routing through ``use_technique``
(rather than a generic shared check) means the check is sourced from the
player's actual technique (``technique.action_template.check_type``),
anima/Soulfray/mishap apply normally, and Audere/Audere Majora escalation
fires automatically (it's wired inside ``use_technique`` itself, Step 8c — no
separate call site is needed here). ``resolve_battle_round`` calls
``resolve_battle_technique`` per declaration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.battles.constants import (
    BASE_FAILURE_DAMAGE,
    ROUTED_STRENGTH_THRESHOLD,
    STRIKE_ATTRITION_PER_LEVEL,
    STRIKE_VP_PER_LEVEL,
    SUPPORT_VP,
    BattleActionKind,
    BattleUnitStatus,
)
from world.battles.models import BattleParticipant, BattleRound
from world.checks.services import perform_check
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ConsequencePool
    from world.battles.models import Battle, BattleActionDeclaration
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.conditions.models import ConditionInstance
    from world.magic.models import Technique
    from world.magic.types.power_ledger import PowerLedger


def _is_isolated(participant: BattleParticipant) -> bool:
    """True when no other ACTIVE participant on the same side shares this participant's place.

    A participant with no ``place`` assigned (front-agnostic) is never counted as
    isolated — isolation is specifically about being alone at a front, not merely
    unassigned.
    """
    from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415

    if participant.place_id is None:
        return False
    return (
        not BattleParticipant.objects.filter(
            battle_id=participant.battle_id,
            side_id=participant.side_id,
            place_id=participant.place_id,
            status=BattleParticipantStatus.ACTIVE,
        )
        .exclude(pk=participant.pk)
        .exists()
    )


def _has_unimpaired_mobility(character_sheet: CharacterSheet) -> bool:
    """True when the character's MOVEMENT capability is currently unimpaired.

    Resolved the same way ``can_act`` resolves AWARENESS — via
    ``get_effective_capability_value`` — rather than the room-based positioning-graph
    ``blocks_flight``/``elevation_anchor`` fields, which don't apply to location-less
    battles (see the #1733 spec's anti-reinvention ledger).
    """
    from world.conditions.constants import FoundationalCapability  # noqa: PLC0415
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.conditions.services import get_effective_capability_value  # noqa: PLC0415

    movement = CapabilityType.objects.filter(name=FoundationalCapability.MOVEMENT).first()
    if movement is None:
        return False
    return get_effective_capability_value(character_sheet, movement) > 0


def select_surrounded_terminal_pool(
    *, battle: Battle, participant: BattleParticipant
) -> ConsequencePool | None:
    """Route the Surrounded terminal resolution to the enemy or PvP-safe pool (#1733).

    Death is permitted by default (``surrounded_terminal_enemy`` — the isolating side is
    normally an abstract, non-PC ``BattleUnit``) UNLESS the opposing ``BattleSide`` has an
    active PC participant at the same ``place`` — an actual PC opponent present means
    ADR-0023 (PvP non-lethal) applies, so ``surrounded_terminal_pvp`` (no death row at
    all) is used instead. This replaces ``select_abandonment_pool``'s ``ObjectDB``
    source-character routing, which doesn't apply here (see Task 2).

    Returns ``None`` on a seeding gap (the named pool doesn't exist) rather than raising
    — matches the "never crash the round, hold the victim" convention the sibling
    ``_resolve_terminal_bleed_out`` already follows (final-review finding: this runs
    inside ``resolve_battle_round``'s ``@transaction.atomic``, so raising here would
    abort the GM's entire round resolution, not just this one victim's outcome).
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
    from world.vitals.constants import (  # noqa: PLC0415
        POOL_SURROUNDED_TERMINAL_ENEMY,
        POOL_SURROUNDED_TERMINAL_PVP,
    )

    opposing_pc_present = (
        BattleParticipant.objects.filter(
            battle_id=battle.pk,
            place_id=participant.place_id,
            status=BattleParticipantStatus.ACTIVE,
        )
        .exclude(side_id=participant.side_id)
        .filter(character_sheet__character__db_account__isnull=False)
        .exists()
    )
    pool_name = (
        POOL_SURROUNDED_TERMINAL_PVP if opposing_pc_present else POOL_SURROUNDED_TERMINAL_ENEMY
    )
    return ConsequencePool.objects.filter(name=pool_name).first()


def resolve_surrounded_terminal(
    *, character_sheet: CharacterSheet, instance: ConditionInstance, battle: Battle
) -> bool:
    """Resolve a terminal-stage Surrounded instance through the routed, guarded pool.

    Finds the character's ``BattleParticipant`` for ``battle`` to route via
    ``select_surrounded_terminal_pool``, checks ``has_death_deferred`` explicitly (the
    part of ``death_is_permitted`` that's still relevant — a deferred-death condition
    protects the victim regardless of who/what surrounded them), then dispatches through
    the shared ``_resolve_peril_via_pool`` core (Task 2).

    A missing ``BattleParticipant`` (shouldn't happen — the caller always has one) or a
    missing terminal pool (seeding gap) holds the victim rather than crashing.
    """
    from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
    from world.conditions.services import has_death_deferred  # noqa: PLC0415
    from world.vitals.services import _resolve_peril_via_pool  # noqa: PLC0415

    participant = BattleParticipant.objects.filter(
        battle=battle,
        character_sheet=character_sheet,
        status=BattleParticipantStatus.ACTIVE,
    ).first()
    if participant is None:
        return False

    pool = select_surrounded_terminal_pool(battle=battle, participant=participant)
    if pool is None:
        return False
    death_permitted = not has_death_deferred(character_sheet.character)

    died = _resolve_peril_via_pool(character_sheet, instance, pool, death_permitted=death_permitted)
    if died:
        participant.status = BattleParticipantStatus.INCAPACITATED
        participant.save(update_fields=["status"])
    return died


@dataclass
class BattleTechniqueResolution:
    """Adapts ``use_technique``'s resolve_fn contract — exposes ``.check_result``
    for ``_resolve_check_result`` (``world/magic/services/techniques.py``)."""

    check_result: CheckResult


@dataclass
class BattleTechniqueResolver:
    """``resolve_fn`` passed to ``use_technique``: rolls the declared technique's
    own check. Battle has no damage-profile/condition application of its own —
    that stays in ``resolve_battle_round``'s STRIKE/SUPPORT/failure routing.
    """

    character: ObjectDB
    technique: Technique

    def __call__(
        self,
        *,
        power: int,  # noqa: ARG002 — battle doesn't scale effects off cast power
        ledger: PowerLedger,  # noqa: ARG002 — battle doesn't use the power ledger
        extra_modifiers: int = 0,
    ) -> BattleTechniqueResolution:
        check_type = self.technique.action_template.check_type
        check_result = perform_check(self.character, check_type, extra_modifiers=extra_modifiers)
        return BattleTechniqueResolution(check_result=check_result)


def resolve_battle_technique(*, declaration: BattleActionDeclaration) -> CheckResult | None:
    """Cast ``declaration.technique`` through the real magic envelope.

    Routes through ``use_technique`` so anima cost, Soulfray accumulation, and —
    critically — the Audere/Audere Majora escalation hook (Step 8c, fires
    unconditionally inside ``use_technique`` for every caller) all apply exactly
    as they would for any other cast. ``confirm_soulfray_risk=True`` because a
    batch round resolve cannot pause mid-batch for one participant's consent
    prompt — same reasoning ``resolve_accepted_cast`` uses for its consent-accept
    path.

    Args:
        declaration: A ``BattleActionDeclaration`` with ``technique`` set.

    Returns:
        The resolved ``CheckResult``, or ``None`` if the cast was interrupted
        before resolution (e.g. a reactive PRE_CAST cancellation) — the caller
        treats ``None`` as success_level 0 (failure).
    """
    from world.magic.services import use_technique  # noqa: PLC0415

    character = declaration.participant.character_sheet.character
    technique = declaration.technique
    resolver = BattleTechniqueResolver(character=character, technique=technique)

    result = use_technique(
        character=character,
        technique=technique,
        resolve_fn=resolver,
        confirm_soulfray_risk=True,
        # lethal defaults True (unlike combat's lethal=encounter.is_lethal) — battles
        # have no non-lethal encounter concept; this only bounds the CASTER's own
        # anima-overburn/Soulfray severity, not PvP damage (ADR-0023 is unaffected).
    )
    if not result.confirmed or result.resolution_result is None:
        # PRE_CAST cancellation (rare, e.g. a reactive scar) — no anima was spent,
        # but the caller still counts this as a failure (success_level 0) for
        # simplicity; the round-scale batch resolve has no cheaper alternative.
        return None
    return result.resolution_result.check_result


@dataclass
class BattleRoundResult:
    """Summary of a resolved battle round."""

    # VP awarded per BattleSide pk → total awarded this round.
    vp_awarded: dict[int, int] = field(default_factory=dict)
    # Units whose strength reached 0 and were DESTROYED this round.
    units_destroyed: list[int] = field(default_factory=list)
    # Units whose strength fell below the ROUTED threshold (but not 0).
    units_routed: list[int] = field(default_factory=list)
    # Participant pks who took damage this round.
    casualties: list[int] = field(default_factory=list)


def _resolve_strike_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
) -> None:
    """Apply STRIKE success: attrite the unit, award VP to the participant's side."""
    unit = declaration.target_unit
    if unit is None:
        return

    attrition = success_level * STRIKE_ATTRITION_PER_LEVEL
    unit.strength = max(0, unit.strength - attrition)

    if unit.strength == 0:
        unit.status = BattleUnitStatus.DESTROYED
        result.units_destroyed.append(unit.pk)
    elif unit.strength <= ROUTED_STRENGTH_THRESHOLD:
        unit.status = BattleUnitStatus.ROUTED
        result.units_routed.append(unit.pk)

    unit.save(update_fields=["strength", "status"])

    side = declaration.participant.side
    vp_gain = success_level * STRIKE_VP_PER_LEVEL
    side.victory_points += vp_gain
    side.save(update_fields=["victory_points"])

    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + vp_gain


def _resolve_support_success(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
) -> None:
    """Apply SUPPORT success: award SUPPORT_VP to the participant's side."""
    side = declaration.participant.side
    side.victory_points += SUPPORT_VP
    side.save(update_fields=["victory_points"])
    result.vp_awarded[side.pk] = result.vp_awarded.get(side.pk, 0) + SUPPORT_VP


def _resolve_rescue_success(declaration: BattleActionDeclaration) -> None:
    """Apply RESCUE success: clear the target ally's Surrounded condition (#1733).

    No VP awarded — rescue trades round economy for saving an ally, not battlefield
    progress. No-op if the target ally isn't (or is no longer) Surrounded — a second
    rescue declaration on an already-clear ally is simply wasted, not an error.
    """
    from world.conditions.constants import SURROUNDED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import get_active_conditions, remove_condition  # noqa: PLC0415

    target = declaration.target_ally
    if target is None:
        return

    template = ConditionTemplate.objects.filter(name=SURROUNDED_CONDITION_NAME).first()
    if template is None:
        return

    character = target.character_sheet.character
    if get_active_conditions(character, condition=template).exists():
        remove_condition(character, template)


def _maybe_apply_surrounded(declaration: BattleActionDeclaration) -> bool:
    """Roll the surrounded_entry pool for an isolated declaration failure (#1733).

    Isolation and mobility are objective, code-computed signals fed as extra_modifiers
    into the entry check — the pool's authored rows decide the actual odds (never a
    hardcoded gate; see Decision 3 of the #1733 spec). No-op when the pool/condition
    content isn't seeded (degrades gracefully, same convention as the abandonment pools).

    Returns True iff Surrounded was newly applied this call — the caller propagates
    this so ``resolve_battle_round`` can exclude a participant from this same round's
    escalation tick (final-review finding: a participant always declared to reach this
    failure branch, so without the exclusion a freshly-Surrounded participant would
    immediately roll their first escalation check in the very round they entered,
    rather than getting one round before their peril first escalates).
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.battles.constants import (  # noqa: PLC0415
        SURROUNDED_ENTRY_ISOLATED_MODIFIER,
        SURROUNDED_ENTRY_MOBILITY_MODIFIER,
    )
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        resolve_pool_consequences,
        select_consequence,
    )
    from world.conditions.constants import SURROUNDED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionStage, ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.vitals.constants import POOL_SURROUNDED_ENTRY  # noqa: PLC0415

    participant = declaration.participant
    if not _is_isolated(participant):
        return False

    pool = ConsequencePool.objects.filter(name=POOL_SURROUNDED_ENTRY).first()
    template = ConditionTemplate.objects.filter(name=SURROUNDED_CONDITION_NAME).first()
    entry_stage = (
        ConditionStage.objects.filter(condition=template, stage_order=1).first()
        if template is not None
        else None
    )
    if pool is None or template is None or entry_stage is None:
        return False

    extra_modifiers = SURROUNDED_ENTRY_ISOLATED_MODIFIER
    if _has_unimpaired_mobility(participant.character_sheet):
        extra_modifiers += SURROUNDED_ENTRY_MOBILITY_MODIFIER

    character = participant.character_sheet.character
    candidates = resolve_pool_consequences(pool)
    pending = select_consequence(
        character,
        entry_stage.resist_check_type,
        entry_stage.resist_difficulty,
        candidates,
        extra_modifiers=extra_modifiers,
    )
    if pending.selected_consequence.label == "surrounded":  # noqa: STRING_LITERAL
        # No `stage` kwarg on apply_condition — the has_progression=True template
        # auto-initializes current_stage to stage_order=1 (== entry_stage) via
        # _build_bulk_context (world/conditions/services.py:483).
        apply_condition(target=character, condition=template)
        return True
    return False


def _resolve_failure(
    declaration: BattleActionDeclaration,
    result: BattleRoundResult,
    success_level: int,
) -> bool:
    """Apply check failure: debit PC health, route through damage consequences, and
    roll the surrounded_entry pool if the participant is isolated (#1733).

    Damage is non-progressive (damage_type=None, source_character=None) so
    the SQLite fast tier can handle it without DISTINCT ON queries.

    Returns True iff Surrounded was newly applied this call (propagated from
    ``_maybe_apply_surrounded`` — see its docstring for why the caller needs this).
    """
    from world.vitals.models import CharacterVitals  # noqa: PLC0415
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    sheet = declaration.participant.character_sheet
    try:
        vitals = sheet.vitals
    except CharacterVitals.DoesNotExist:
        result.casualties.append(declaration.participant.pk)
        return False

    dmg = BASE_FAILURE_DAMAGE + abs(success_level)
    vitals.health -= dmg
    vitals.save(update_fields=["health"])

    process_damage_consequences(
        character_sheet=sheet,
        damage_dealt=dmg,
        damage_type=None,
        source_character=None,
    )
    newly_surrounded = _maybe_apply_surrounded(declaration)
    result.casualties.append(declaration.participant.pk)
    return newly_surrounded


def _advance_surrounded_participants(
    battle: Battle,
    declared_participant_ids: set[int],
    newly_surrounded_participant_ids: set[int],
) -> None:
    """Tick every ACTIVE Surrounded participant's peril once for this round (#1733).

    A participant advances if they declared this round, OR ``battle.afk_peril_override``
    is True (the narrow, explicit ADR-0004 exception — see ADR-0070). Otherwise their
    peril holds unchanged this round — mirroring the intent of the room-based #1480
    own-peril skip without depending on SceneRound (Decision 1 of the #1733 spec).

    ``newly_surrounded_participant_ids`` are always excluded regardless of the above —
    a participant only reaches this tier by declaring (isolated + failed), so without
    this exclusion a freshly-Surrounded participant would immediately roll their first
    escalation check in the very round they entered Surrounded, rather than getting one
    round before their peril first escalates (final-review finding).
    """
    from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
    from world.conditions.constants import SURROUNDED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import get_active_conditions  # noqa: PLC0415
    from world.vitals.services import advance_surrounded  # noqa: PLC0415

    template = ConditionTemplate.objects.filter(name=SURROUNDED_CONDITION_NAME).first()
    if template is None:
        return  # seeding gap — nothing to advance

    participants = BattleParticipant.objects.filter(
        battle=battle, status=BattleParticipantStatus.ACTIVE
    ).select_related("character_sheet__character")

    for participant in participants:
        if participant.pk in newly_surrounded_participant_ids:
            continue
        if not (battle.afk_peril_override or participant.pk in declared_participant_ids):
            continue
        sheet = participant.character_sheet
        if not get_active_conditions(sheet.character, condition=template).exists():
            continue
        advance_surrounded(sheet, battle=battle)


@transaction.atomic
def resolve_battle_round(*, battle_round: BattleRound) -> BattleRoundResult:
    """Resolve all unresolved declarations for ``battle_round``.

    For each unresolved declaration, casts its declared technique through
    ``resolve_battle_technique`` (the real magic envelope) and routes
    success / failure to the appropriate sub-handlers. Before marking the
    round complete, ticks every ACTIVE Surrounded participant's peril once
    via ``_advance_surrounded_participants`` (#1733) — gated by declaration
    this round or ``battle.afk_peril_override``. Sets
    ``battle_round.status = COMPLETED`` at the end.

    Args:
        battle_round: The ``BattleRound`` in DECLARING or RESOLVING status.

    Returns:
        A ``BattleRoundResult`` summarising what happened this round.
    """
    result = BattleRoundResult()

    declarations = list(
        battle_round.declarations.filter(resolved=False).select_related(
            "participant__character_sheet",
            "participant__side",
            "target_unit",
            "technique__action_template",
        )
    )

    newly_surrounded_participant_ids: set[int] = set()
    for declaration in declarations:
        check_result = resolve_battle_technique(declaration=declaration)
        sl = check_result.success_level if check_result is not None else 0

        if sl > 0:
            if declaration.action_kind == BattleActionKind.STRIKE:
                _resolve_strike_success(declaration, result, sl)
            elif declaration.action_kind == BattleActionKind.RESCUE:
                _resolve_rescue_success(declaration)
            else:
                _resolve_support_success(declaration, result)
        elif _resolve_failure(declaration, result, sl):
            newly_surrounded_participant_ids.add(declaration.participant_id)

        declaration.resolved = True
        declaration.success_level = sl
        declaration.save(update_fields=["resolved", "success_level"])

    declared_participant_ids = {d.participant_id for d in declarations}
    _advance_surrounded_participants(
        battle_round.battle, declared_participant_ids, newly_surrounded_participant_ids
    )

    battle_round.status = RoundStatus.COMPLETED
    battle_round.completed_at = timezone.now()
    battle_round.save(update_fields=["status", "completed_at"])

    return result
