"""The read seam for vow added effects: which rows fire for a cast, and applying them (#4581).

A ``VowAddedEffect`` is staff-authored payload a covenant vow adds to the casts
its row matches. Both cast paths (the combat technique resolver and the
out-of-combat cast) call into this module:

- ``vow_added_effects_for_cast`` picks the rows that fire for one cast and
  scales their bonuses, returning ``FiredVowEffect`` values.
- ``apply_vow_effect_payloads`` hands each fired row's applied conditions,
  treatments and removed conditions to the technique payload seams in
  ``world.magic.services.condition_application``.
- ``vow_damage_profiles`` pairs each fired row's damage profiles with its
  damage bonus, for the combat damage step.
- ``record_vow_effect_firings`` spends once-per-round and once-per-fight rows
  in the ``VowAddedEffectFiring`` ledger. The caller writes it only after a
  cast lands, so a failed cast never spends a limited effect.
- ``vow_added_effects_on_technique`` is the static view for display (#4565).

## Who holds a row

The holders are the ones situational perks use (``vow_holder_candidates``):
the caster's own engaged vows (anchor role plus resolved sub-role, a secondary
vow's anchor only) and every co-present covenant ally's vows. A row rides a
cast when its ``beneficiary`` counts for that holder: SELF and WHOLE_GROUP on
the caster's own vow, COVENANT_ALLIES and WHOLE_GROUP on an ally's.

## Scaling

The holder's COVENANT_ROLE thread level on the vow's anchor role gates the row
(``unlock_thread_level``) and scales it: each level above the unlock adds the
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
4. Thread levels, the in-combat flag and one ``SituationCheck``.
5. The per-holder gates, the situation last.
6. The upgrade rule, per holder.
7. In combat, the frequency ledger (one query, only when a live row is limited).
8. Dedupe on ``(holder, row)``.
9. The thread-level bonuses, potency-scaled for a secondary vow.

## Query discipline

Every cast in the game calls ``vow_added_effects_for_cast``, so the order is
fixed to keep the common cast cheap: a technique with no function tag returns
before any query, and a caster with no engaged vow and no co-present holder
returns before the ``VowAddedEffect`` query. Past that it is one row query plus
four payload prefetches (whatever the row count), one thread-level query, the
situations the live rows name, and, in combat, one ledger query when a live
row is limited.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import Prefetch, Q

from world.combat.models import CombatParticipant, VowAddedEffectFiring
from world.covenants.constants import VowEffectContext, VowEffectFrequency
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
from world.magic.models.techniques import ConditionTargetKind

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter
    from world.conditions.types import AppliedConditionResult, RemovedConditionResult
    from world.magic.models import Technique
    from world.scenes.models import Scene

#: Frequencies spent through the ``VowAddedEffectFiring`` ledger.
_LIMITED_FREQUENCIES = frozenset(
    {VowEffectFrequency.ONCE_PER_ROUND, VowEffectFrequency.ONCE_PER_FIGHT}
)


@dataclass(frozen=True)
class _LiveRow:
    """One row that passed the cast-time gates for one holder candidate."""

    candidate: VowHolderCandidate
    effect: VowAddedEffect
    thread_level: int


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
    situation holds for the holder. Then the upgrade rule (see the module
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
    sheet's own casts from one riding its allies'.
    """
    functions = {tag.function for tag in technique.cached_function_tags}
    if not functions:
        return []
    candidates = _self_candidates(sheet)
    if not candidates:
        return []
    return list(
        VowAddedEffect.objects.filter(
            Q(gift__isnull=True) | Q(gift_id=technique.gift_id),
            Q(technique__isnull=True) | Q(technique_id=technique.pk),
            covenant_role_id__in={c.role_id for c in candidates},
            function__in=functions,
        )
    )


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
    out-of-combat map holds only the technique's own target relationship. Each
    fired row's applied conditions go to ``apply_technique_conditions`` with the
    row's severity and duration bonus, then its treatments to
    ``apply_technique_treatments``, then its removed conditions to
    ``remove_technique_conditions``; a payload list that is empty is skipped.
    ``technique`` stays the provenance on everything applied. Returns the
    applied and removed condition results, in firing order.
    """
    from world.magic.services.condition_application import (  # noqa: PLC0415
        apply_technique_conditions,
        apply_technique_treatments,
        remove_technique_conditions,
    )

    targets = {**targets_by_kind, ConditionTargetKind.SELF: [source_character]}
    applied: list[AppliedConditionResult] = []
    removed: list[RemovedConditionResult] = []
    for firing in fired:
        effect = firing.effect
        if effect.cached_applied_conditions:
            applied.extend(
                apply_technique_conditions(
                    technique=technique,
                    success_level=success_level,
                    eff_intensity=eff_intensity,
                    targets_by_kind=targets,
                    source_character=source_character,
                    applied_condition_rows=effect.cached_applied_conditions,
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
        if effect.cached_removed_conditions:
            removed.extend(
                remove_technique_conditions(
                    technique=technique,
                    success_level=success_level,
                    eff_intensity=eff_intensity,
                    targets_by_kind=targets,
                    source_character=source_character,
                    removed_condition_rows=effect.cached_removed_conditions,
                )
            )
    return applied, removed


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
    ).prefetch_related(
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
    by_role: dict[int, list[VowAddedEffect]] = {}
    for effect in effects:
        by_role.setdefault(effect.covenant_role_id, []).append(effect)
    return by_role


def _live_rows(  # noqa: PLR0913 - the cast's gates, computed once by the caller
    candidates: list[VowHolderCandidate],
    effects_by_role: dict[int, list[VowAddedEffect]],
    *,
    technique: Technique,
    levels: dict[tuple[int, int], int],
    in_combat: bool,
    check: SituationCheck,
) -> list[_LiveRow]:
    """Rows that pass every per-holder gate; the situation is checked last (it may query)."""
    live: list[_LiveRow] = []
    for candidate in candidates:
        level = levels.get((candidate.holder.pk, candidate.anchor_role_id), 0)
        live.extend(
            _LiveRow(candidate=candidate, effect=effect, thread_level=level)
            for effect in effects_by_role.get(candidate.role_id, ())
            if (
                effect.beneficiary in candidate.beneficiaries
                and effect.gift_id in (None, technique.gift_id)
                and effect.technique_id in (None, technique.pk)
                and _context_allows(effect.cast_context, in_combat=in_combat)
                and level >= effect.unlock_thread_level
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

    The secondary potency config is read at most once, and only when a
    secondary-sourced row fires.
    """
    potency_tenths: int | None = None
    fired: list[FiredVowEffect] = []
    seen: set[tuple[int, int]] = set()
    for row in live:
        effect = row.effect
        key = (row.candidate.holder.pk, effect.pk)
        if key in seen:
            continue
        seen.add(key)

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
