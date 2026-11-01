"""The read seam for vow added effects: which rows fire for a cast, and applying them (#4581).

A ``VowAddedEffect`` is staff-authored payload a covenant vow adds to the casts
its row matches. Both cast paths (the combat technique resolver and the
out-of-combat cast) call into this module:

- ``vow_added_effects_for_cast`` picks the rows that fire for one cast and
  scales their bonuses, returning ``FiredVowEffect`` values.
- ``apply_vow_effect_payloads`` hands each fired row's applied conditions,
  treatments and removed conditions to the technique payload seams in
  ``world.magic.services.condition_application``: every row's conditions and
  treatments first, then every row's removals. Both cast paths call it after
  the technique's own treatments and before its own removals.
- ``vow_damage_profiles`` pairs each fired row's damage profiles with its
  damage bonus, for the combat damage step.
- ``record_vow_effect_firings`` spends once-per-round and once-per-fight rows
  in the ``VowAddedEffectFiring`` ledger. The caller writes it only after a
  cast lands, so a failed cast never spends a limited effect.
- ``vow_added_effects_on_technique`` is the static view for display (#4565).
- ``effect_rides_technique`` and ``techniques_ridden_by`` are the one catalog
  match between a row and the techniques it rides (function tag, then the gift
  or technique narrowing), shared by the cast path, the static view and the
  vow page's rail (#4880).

## Who holds a row

The holders are the ones situational perks use (``vow_holder_candidates``):
the caster's own engaged vows (anchor role plus resolved sub-role, a secondary
vow's anchor only) and every co-present covenant ally's vows. A row rides a
cast when its ``beneficiary`` counts for that holder: SELF and WHOLE_GROUP on
the caster's own vow, COVENANT_ALLIES and WHOLE_GROUP on an ally's.

## Focus picks

A row whose ``focus_pick`` is set fires only for a holder who chose that pick
(``CharacterVowFocusPick``, #4759). A row with no pick is the base vow and fires
for every holder. The chosen picks are read in one query, and only when a
fetched row carries a pick, so a vow with no picks costs nothing extra. A pick
row that a holder did not choose is not live, so a base row it ``upgrades``
stays in place for that holder.

## Scaling

The holder's COVENANT_ROLE thread level on the vow's anchor role, shown scale
(stored // 10, #4585), gates the row (``unlock_thread_level``) and scales it:
each shown level above the unlock adds the
row's ``severity_per_thread_level``, ``duration_per_thread_level`` and
``damage_per_thread_level``. A row from a secondary vow has each bonus
multiplied by ``SecondaryVowConfig.potency_tenths`` and floor-divided by 10.

## Upgrades

A live row whose ``upgrades`` names another live row of the same holder
replaces it: a resonance sub-role's version of its anchor's row, or a
later-unlock row on the same role. Every other row adds.

"Live" here means the row passed the cast's gates (beneficiary, narrowing,
context, unlock level, situation). An upgrade that fails one of them leaves its
base in place. The frequency ledger is checked AFTER the upgrade rule, so a
spent once-per-round or once-per-fight upgrade still replaces its base: the
base never fires again just because its upgrade is used up.

## Order of the steps

1. The technique's function tags; none returns ``[]``.
2. The holder candidates; none returns ``[]``.
3. One ``VowAddedEffect`` query with the four payload prefetches; none returns ``[]``.
4. Thread levels, the chosen focus picks (only when a row has one), the in-combat
   flag and one ``SituationCheck``.
5. The per-holder gates, the situation last.
6. The upgrade rule, per holder.
7. In combat, the frequency ledger (one query, only when a live row is limited).
8. Dedupe on ``(holder, row)``; a primary candidate wins over a secondary one.
9. The thread-level bonuses, potency-scaled for a secondary vow.

## Query discipline

Every cast in the game calls ``vow_added_effects_for_cast``, so the order is
fixed to keep the common cast cheap: a technique with no function tag returns
before any query, and a caster with no engaged vow and no co-present holder
returns before the ``VowAddedEffect`` query. Past that it is one row query plus
four payload prefetches (whatever the row count), one thread-level query, one
chosen-pick query when a fetched row carries a focus pick, the situations the
live rows name, and, in combat, one ledger query when a live
row is limited.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from django.db.models import Prefetch, QuerySet

from world.combat.models import CombatParticipant, VowAddedEffectFiring
from world.covenants.constants import VowEffectContext, VowEffectFrequency
from world.covenants.focus_picks import chosen_pick_ids_by_holder, holder_has_pick
from world.covenants.models import (
    VowAddedEffect,
    VowAddedEffectAppliedCondition,
    VowAddedEffectDamageProfile,
    VowAddedEffectRemovedCondition,
    VowAddedEffectTreatment,
)
from world.covenants.perks.evaluators import _resolution_participant
from world.covenants.perks.services import (
    SituationCheck,
    VowHolderCandidate,
    _self_candidates,
    vow_holder_candidates,
    vow_holder_thread_levels,
)
from world.covenants.types import FiredVowEffect
from world.magic.models.techniques import ConditionTargetKind, Technique, TechniqueFunctionTag

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter
    from world.conditions.types import AppliedConditionResult, RemovedConditionResult
    from world.scenes.models import Scene

logger = logging.getLogger(__name__)

#: Frequencies spent through the ``VowAddedEffectFiring`` ledger.
_LIMITED_FREQUENCIES = frozenset(
    {VowEffectFrequency.ONCE_PER_ROUND, VowEffectFrequency.ONCE_PER_FIGHT}
)


@dataclass(frozen=True)
class _LiveRow:
    """One row that passed the cast-time gates for one holder candidate."""

    candidate: VowHolderCandidate
    effect: VowAddedEffect
    thread_level: int  # shown level (stored // 10, #4585)


def effect_rides_technique(
    effect: VowAddedEffect, technique: Technique, technique_functions: set[str]
) -> bool:
    """True when ``effect`` rides casts of ``technique``, by the catalog match alone (#4880).

    ``technique_functions`` is the technique's function tags (the caller reads them
    once). The row's ``function`` must be one of them, and its gift and technique
    narrowing, when set, must name the technique's gift or the technique itself.
    Nothing that depends on a cast or a holder is read here.
    """
    return (
        effect.function in technique_functions
        and effect.gift_id in (None, technique.gift_id)
        and effect.technique_id in (None, technique.pk)
    )


def techniques_by_function(functions: Iterable[str]) -> dict[str, list[Technique]]:
    """Every catalog technique carrying each of ``functions``, by name: one query (#4880).

    The function-tag half of the match, for a reader that needs many groups at once (the
    vow page's rail and its specialty rows); narrow each list with
    ``effect_rides_technique`` for an added effect.
    """
    wanted = set(functions)
    by_function: dict[str, list[Technique]] = {function: [] for function in wanted}
    if not wanted:
        return by_function
    tags = (
        TechniqueFunctionTag.objects.filter(function__in=wanted)
        .select_related("technique")
        .order_by("technique__name")
    )
    for tag in tags:
        by_function[tag.function].append(tag.technique)
    return by_function


def techniques_ridden_by(effect: VowAddedEffect) -> QuerySet[Technique]:
    """Every catalog technique ``effect`` rides: the queryset form of the match (#4880).

    Techniques carrying a function tag equal to the row's ``function``, narrowed to
    the row's gift or its one technique when set. Ordered by name.
    """
    techniques = Technique.objects.filter(function_tags__function=effect.function)
    if effect.technique_id is not None:
        techniques = techniques.filter(pk=effect.technique_id)
    elif effect.gift_id is not None:
        techniques = techniques.filter(gift_id=effect.gift_id)
    return techniques.distinct().order_by("name")


def vow_added_effects_for_cast(
    subject: CharacterSheet,
    technique: Technique,
    *,
    resolution: object | None,
    target: CharacterSheet | None,
) -> list[FiredVowEffect]:
    """Every ``VowAddedEffect`` that fires for ``subject`` casting ``technique`` right now.

    ``resolution`` is the cast's live resolution context (a ``CombatRoundContext``
    in combat, ``None`` out of it); a cast is in combat when it carries a
    participant. ``target`` is the cast's target sheet, or ``None``, for the
    rows' situations.

    A row fires when its role is one a holder candidate answers for, its
    ``function`` is one of the technique's function tags, and all of these
    hold: the beneficiary counts for that holder; the gift and technique
    narrowing (when set) match; the cast context matches; the holder's thread
    level on the anchor role reaches ``unlock_thread_level``; the row's
    situation holds for the holder; a row with a ``focus_pick`` also needs the
    holder to have chosen that pick. Then the upgrade rule (see the module
    docstring) runs over those live rows. Then, in combat, a once-per-round row
    already in the ledger for this round, or a once-per-fight row in the ledger
    for this fight, is dropped. Last, one holder fires one row at most once.
    """
    functions = {tag.function for tag in technique.cached_function_tags}
    if not functions:
        return []

    candidates = vow_holder_candidates(subject, resolution)
    if not candidates:
        return []

    effects_by_role = _fetch_effects({c.role_id for c in candidates}, functions)
    if not effects_by_role:
        return []

    participant = _resolution_participant(resolution)
    live = _live_rows(
        candidates,
        effects_by_role,
        technique=technique,
        levels=vow_holder_thread_levels(candidates),
        chosen_picks=_chosen_picks_for(candidates, effects_by_role),
        in_combat=participant is not None,
        check=SituationCheck(subject=subject, target=target, resolution=resolution),
    )
    live = _drop_upgraded(live)
    if participant is not None:
        live = _drop_spent(live, encounter=participant.encounter)
    return _scaled_firings(live)


def vow_added_effects_on_technique(
    sheet: CharacterSheet, technique: Technique
) -> list[VowAddedEffect]:
    """The vow added effects authored onto ``technique`` for ``sheet``: the static view.

    Built for #4565's display (the workbench, vow board and spellbook vow
    section), which shows what a character's vows add to a technique without a
    live cast. The sheet's own engaged vows count (anchor role plus resolved
    sub-role, a secondary vow's anchor only); a row is listed when its
    ``function`` is one of the technique's function tags and its gift and
    technique narrowing (when set) match. Nothing that depends on a cast is
    applied: not the unlock level, the context, the situation or the frequency.
    The rows keep their ``beneficiary``, so a display can tell a row riding the
    sheet's own casts from one riding its allies'. A row with a ``focus_pick`` is
    listed only when the sheet chose that pick, since it never rides the sheet's
    casts otherwise.
    """
    functions = {tag.function for tag in technique.cached_function_tags}
    if not functions:
        return []
    candidates = _self_candidates(sheet)
    if not candidates:
        return []
    effects = [
        effect
        for effect in VowAddedEffect.objects.filter(
            covenant_role_id__in={c.role_id for c in candidates}, function__in=functions
        )
        if effect_rides_technique(effect, technique, functions)
    ]
    if not any(effect.focus_pick_id is not None for effect in effects):
        return effects
    chosen = chosen_pick_ids_by_holder({sheet.pk})
    return [effect for effect in effects if holder_has_pick(effect.focus_pick_id, sheet.pk, chosen)]


def apply_vow_effect_payloads(  # noqa: PLR0913 - the payload seams' own parameters
    fired: Sequence[FiredVowEffect],
    *,
    technique: Technique,
    success_level: int,
    eff_intensity: int,
    targets_by_kind: dict[str, list[ObjectDB]],  # noqa: OBJECTDB_PARAM
    source_character: ObjectDB,  # noqa: OBJECTDB_PARAM
    scene: Scene,
    soulfray_consented: bool = False,
) -> tuple[list[AppliedConditionResult], list[RemovedConditionResult]]:
    """Apply every fired row's conditions, treatments and removals for one cast.

    ``targets_by_kind`` is the cast's own resolved target map; SELF is always
    mapped to the caster (``source_character``) over a copy of it, since the
    out-of-combat map holds only the technique's own target relationship.

    Two passes over the fired rows. First, each row's applied conditions go to
    ``apply_technique_conditions`` with the row's severity and duration bonus,
    then its treatments to ``apply_technique_treatments``. Second, every row's
    removed conditions go to ``remove_technique_conditions``. So every vow
    treatment runs before any vow removal, the cast pipeline's own "treatments
    before removals" rule (a removal must not strip the wound a treatment
    mends). Both cast paths call this after the technique's own treatments and
    before its own removals, which keeps that rule across the whole cast. A
    payload list that is empty is skipped. ``technique`` stays the provenance on
    everything applied.

    An applied condition whose category ``alters_behavior`` is skipped here as
    well as refused in authoring (``VowAddedEffectAppliedCondition.clean``): a
    category can gain the flag, or a condition can move category, after the row
    was saved, and consent folding never sees a vow row (ADR-4581-A). Returns
    the applied and removed condition results, in firing order.
    """
    from world.magic.services.condition_application import (  # noqa: PLC0415
        apply_technique_conditions,
        apply_technique_treatments,
        remove_technique_conditions,
    )

    targets = {**targets_by_kind, ConditionTargetKind.SELF: [source_character]}
    applied: list[AppliedConditionResult] = []
    for firing in fired:
        effect = firing.effect
        condition_rows = _consent_free_condition_rows(effect)
        if condition_rows:
            applied.extend(
                apply_technique_conditions(
                    technique=technique,
                    success_level=success_level,
                    eff_intensity=eff_intensity,
                    targets_by_kind=targets,
                    source_character=source_character,
                    applied_condition_rows=condition_rows,
                    soulfray_consented=soulfray_consented,
                    severity_bonus=firing.severity_bonus,
                    duration_bonus=firing.duration_bonus,
                )
            )
        if effect.cached_treatments:
            apply_technique_treatments(
                technique=technique,
                success_level=success_level,
                eff_intensity=eff_intensity,
                targets_by_kind=targets,
                source_character=source_character,
                scene=scene,
                treatment_rows=effect.cached_treatments,
            )

    removed: list[RemovedConditionResult] = []
    for firing in fired:
        if firing.effect.cached_removed_conditions:
            removed.extend(
                remove_technique_conditions(
                    technique=technique,
                    success_level=success_level,
                    eff_intensity=eff_intensity,
                    targets_by_kind=targets,
                    source_character=source_character,
                    removed_condition_rows=firing.effect.cached_removed_conditions,
                )
            )
    return applied, removed


def _consent_free_condition_rows(effect: VowAddedEffect) -> list[VowAddedEffectAppliedCondition]:
    """The row's applied conditions minus any whose category now alters behavior.

    The category is select_related on the cached list, so this issues no query.
    A skipped row is logged for staff: the row needs editing in admin.
    """
    rows: list[VowAddedEffectAppliedCondition] = []
    for row in effect.cached_applied_conditions:
        if row.condition.category.alters_behavior:
            logger.warning(
                "Vow added effect %s skips applied condition %s: its category alters "
                "behavior, which a vow row may never apply (ADR-4581-A).",
                effect.pk,
                row.condition_id,
            )
            continue
        rows.append(row)
    return rows


def vow_damage_profiles(
    fired: Sequence[FiredVowEffect],
) -> list[tuple[VowAddedEffectDamageProfile, int]]:
    """Each fired row's damage profiles, paired with that row's ``damage_bonus``."""
    return [
        (profile, firing.damage_bonus)
        for firing in fired
        for profile in firing.effect.cached_damage_profiles
    ]


def record_vow_effect_firings(
    fired: Sequence[FiredVowEffect], *, encounter: CombatEncounter
) -> int:
    """Spend the fired once-per-round and once-per-fight rows in ``encounter``'s ledger.

    Call it only for a cast that landed, so a failed cast never spends a limited
    effect. Each limited row gets one ``VowAddedEffectFiring`` for its HOLDER's
    participant at ``encounter.round_number``: one ``CombatParticipant`` query for
    the holders, one ``bulk_create``. Every-cast rows write nothing, and with no
    limited row this issues no query. Returns the number of ledger rows written.
    """
    limited = [f for f in fired if f.effect.frequency in _LIMITED_FREQUENCIES]
    if not limited:
        return 0

    participants = {
        participant.character_sheet_id: participant
        for participant in CombatParticipant.objects.filter(
            encounter=encounter, character_sheet_id__in={f.holder.pk for f in limited}
        )
    }
    rows: list[VowAddedEffectFiring] = []
    written: set[tuple[int, int]] = set()
    for firing in limited:
        participant = participants.get(firing.holder.pk)
        if participant is None or (participant.pk, firing.effect.pk) in written:
            continue
        written.add((participant.pk, firing.effect.pk))
        rows.append(
            VowAddedEffectFiring(
                participant=participant,
                effect=firing.effect,
                round_number=encounter.round_number,
            )
        )
    VowAddedEffectFiring.objects.bulk_create(rows)
    return len(rows)


def _fetch_effects(role_ids: set[int], functions: set[str]) -> dict[int, list[VowAddedEffect]]:
    """Every row on ``role_ids`` for ``functions``, keyed by role, payloads prefetched.

    One query plus the four payload prefetches, whatever the row count. A header
    whose cached payload list is already warm keeps it (a child's save or
    delete clears it through ``RelatedCacheClearingMixin``), so an edit made in
    admin is read on the next cast.
    """
    effects = VowAddedEffect.objects.filter(
        covenant_role_id__in=role_ids, function__in=functions
    ).prefetch_related(*payload_prefetches())
    by_role: dict[int, list[VowAddedEffect]] = {}
    for effect in effects:
        by_role.setdefault(effect.covenant_role_id, []).append(effect)
    return by_role


def payload_prefetches() -> tuple[Prefetch, ...]:
    """The four payload prefetches every reader of whole ``VowAddedEffect`` rows uses.

    They fill the rows' ``cached_*`` lists (applied and removed conditions,
    treatments, damage profiles), which the payload seams and the summary line read.
    """
    return (
        Prefetch(
            "applied_conditions",
            queryset=VowAddedEffectAppliedCondition.objects.select_related("condition__category"),
            to_attr="cached_applied_conditions",
        ),
        Prefetch(
            "removed_conditions",
            queryset=VowAddedEffectRemovedCondition.objects.select_related(
                "condition", "condition__cure_check_type"
            ),
            to_attr="cached_removed_conditions",
        ),
        Prefetch(
            "treatments",
            queryset=VowAddedEffectTreatment.objects.select_related(
                "treatment_template__target_condition"
            ),
            to_attr="cached_treatments",
        ),
        Prefetch(
            "damage_profiles",
            queryset=VowAddedEffectDamageProfile.objects.select_related("damage_type"),
            to_attr="cached_damage_profiles",
        ),
    )


def _chosen_picks_for(
    candidates: list[VowHolderCandidate], effects_by_role: dict[int, list[VowAddedEffect]]
) -> dict[int, set[int]]:
    """Each candidate holder's chosen focus picks, or ``{}`` with no query when no
    fetched row carries a pick (#4759 slice 2)."""
    has_pick = any(
        effect.focus_pick_id is not None
        for effects in effects_by_role.values()
        for effect in effects
    )
    if not has_pick:
        return {}
    return chosen_pick_ids_by_holder({c.holder.pk for c in candidates})


def _live_rows(  # noqa: PLR0913 - the cast's gates, computed once by the caller
    candidates: list[VowHolderCandidate],
    effects_by_role: dict[int, list[VowAddedEffect]],
    *,
    technique: Technique,
    levels: dict[tuple[int, int], int],
    chosen_picks: dict[int, set[int]],
    in_combat: bool,
    check: SituationCheck,
) -> list[_LiveRow]:
    """Rows that pass every per-holder gate; the situation is checked last (it may query)."""
    from world.magic.services.threads import shown_thread_level  # noqa: PLC0415

    functions = {tag.function for tag in technique.cached_function_tags}
    live: list[_LiveRow] = []
    for candidate in candidates:
        # unlock_thread_level and the per-level bonuses are on the shown scale (#4585).
        level = shown_thread_level(levels.get((candidate.holder.pk, candidate.anchor_role_id), 0))
        live.extend(
            _LiveRow(candidate=candidate, effect=effect, thread_level=level)
            for effect in effects_by_role.get(candidate.role_id, ())
            if (
                effect.beneficiary in candidate.beneficiaries
                and effect_rides_technique(effect, technique, functions)
                and _context_allows(effect.cast_context, in_combat=in_combat)
                and level >= effect.unlock_thread_level
                and holder_has_pick(effect.focus_pick_id, candidate.holder.pk, chosen_picks)
                and check.holds(effect.situation, effect.params, candidate.holder)
            )
        )
    return live


def _context_allows(cast_context: str, *, in_combat: bool) -> bool:
    """ANY always; IN_COMBAT only in combat; OUT_OF_COMBAT only out of it."""
    if cast_context == VowEffectContext.ANY:
        return True
    return (cast_context == VowEffectContext.IN_COMBAT) == in_combat


def _drop_spent(live: list[_LiveRow], *, encounter: CombatEncounter) -> list[_LiveRow]:
    """Drop limited rows the holder already spent: one ledger query, none without one."""
    limited = [row for row in live if row.effect.frequency in _LIMITED_FREQUENCIES]
    if not limited:
        return live

    ledger = VowAddedEffectFiring.objects.filter(
        participant__encounter_id=encounter.pk,
        participant__character_sheet_id__in={row.candidate.holder.pk for row in limited},
        effect_id__in={row.effect.pk for row in limited},
    ).values_list("participant__character_sheet_id", "effect_id", "round_number")
    spent_this_fight: set[tuple[int, int]] = set()
    spent_this_round: set[tuple[int, int]] = set()
    for sheet_id, effect_id, round_number in ledger:
        spent_this_fight.add((sheet_id, effect_id))
        if round_number == encounter.round_number:
            spent_this_round.add((sheet_id, effect_id))

    def is_spent(row: _LiveRow) -> bool:
        key = (row.candidate.holder.pk, row.effect.pk)
        if row.effect.frequency == VowEffectFrequency.ONCE_PER_FIGHT:
            return key in spent_this_fight
        if row.effect.frequency == VowEffectFrequency.ONCE_PER_ROUND:
            return key in spent_this_round
        return False

    return [row for row in live if not is_spent(row)]


def _drop_upgraded(live: list[_LiveRow]) -> list[_LiveRow]:
    """Drop each live row another live row of the same holder upgrades."""
    replaced = {
        (row.candidate.holder.pk, row.effect.upgrades_id)
        for row in live
        if row.effect.upgrades_id is not None
    }
    return [row for row in live if (row.candidate.holder.pk, row.effect.pk) not in replaced]


def _scaled_firings(live: list[_LiveRow]) -> list[FiredVowEffect]:
    """One ``FiredVowEffect`` per (holder, row), with its thread-level bonuses.

    When one holder reaches the same row through a primary and a secondary
    candidate, the primary one fires (unscaled by the secondary potency), so
    the result never depends on the order the candidates came back in. Firing
    order is the order each (holder, row) was first seen. The secondary potency
    config is read at most once, and only when a secondary-sourced row fires.
    """
    chosen: dict[tuple[int, int], _LiveRow] = {}
    for row in live:
        key = (row.candidate.holder.pk, row.effect.pk)
        kept = chosen.get(key)
        if kept is None or (kept.candidate.is_secondary and not row.candidate.is_secondary):
            chosen[key] = row

    potency_tenths: int | None = None
    fired: list[FiredVowEffect] = []
    for row in chosen.values():
        effect = row.effect
        above = max(0, row.thread_level - effect.unlock_thread_level)
        severity = above * effect.severity_per_thread_level
        duration = above * effect.duration_per_thread_level
        damage = above * effect.damage_per_thread_level
        if row.candidate.is_secondary:
            if potency_tenths is None:
                from world.covenants.services import secondary_vow_config  # noqa: PLC0415

                potency_tenths = secondary_vow_config().potency_tenths
            severity = severity * potency_tenths // 10
            duration = duration * potency_tenths // 10
            damage = damage * potency_tenths // 10
        fired.append(
            FiredVowEffect(
                effect=effect,
                holder=row.candidate.holder,
                is_secondary=row.candidate.is_secondary,
                severity_bonus=severity,
                duration_bonus=duration,
                damage_bonus=damage,
            )
        )
    return fired
