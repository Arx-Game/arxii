"""Derived effect summary for a Technique — the one thing every surface shows (#2898).

A technique's ``Technique`` row carries almost no differentiation; everything that
tells one technique from another lives in four sibling tables
(``TechniqueCapabilityGrant`` / ``TechniqueAppliedCondition`` /
``TechniqueDamageProfile`` / ``TechniqueRemovedCondition``) that no display surface
ever read. This module reads them once and renders them, both as structured data
and as a plain-words line.

It **composes** the two derivations that already existed rather than restating
them: ``is_technique_hostile`` (``services/hostility.py``) and
``derive_target_relationship`` (``services/targeting.py``, already the gate
``validate_cast_target`` runs). No model field is added — per ``Technique
.target_type``'s own help text, relationship is derived, never stored.

Everything here reads the technique's ``cached_*`` payload lists, so the whole
summary costs at most one query per payload table and then rides the
SharedMemoryModel identity map. ``Technique.cached_effect_summary`` caches the
finished payload on the row itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Prefetch

from actions.constants import ActionTargetType
from world.magic.constants import TechniqueReach
from world.magic.models.techniques import (
    ConditionTargetKind,
    Technique,
    TechniqueAppliedCondition,
    TechniqueDamageProfile,
    TechniqueRemovedCondition,
)
from world.magic.services.hostility import is_technique_hostile
from world.magic.services.targeting import derive_target_relationship
from world.magic.types.technique_effects import (
    CapabilityEffectPayload,
    ConditionEffectPayload,
    DamageEffectPayload,
    TechniqueAuthoringGap,
    TechniqueEffectPayload,
)

if TYPE_CHECKING:
    from world.magic.models.techniques import (
        AbstractAppliedCondition,
        AbstractCapabilityGrant,
        AbstractDamageProfile,
    )


# --------------------------------------------------------------------------- #
# Plain-words vocabulary
# --------------------------------------------------------------------------- #

#: Target prose for a technique with nowhere else to land.
_SELF_TARGET_PHRASE = "yourself"

#: How the technique's target reads in prose, keyed on the derived relationship
#: and the authored cardinality. A SELF cardinality always reads "yourself"
#: regardless of what the payload rows derive, since there is no one else to hit.
_TARGET_PHRASES: dict[tuple[str, str], str] = {
    (ConditionTargetKind.SELF, ActionTargetType.SINGLE): _SELF_TARGET_PHRASE,
    (ConditionTargetKind.SELF, ActionTargetType.AREA): _SELF_TARGET_PHRASE,
    (ConditionTargetKind.SELF, ActionTargetType.FILTERED_GROUP): _SELF_TARGET_PHRASE,
    (ConditionTargetKind.ALLY, ActionTargetType.SINGLE): "an ally",
    (ConditionTargetKind.ALLY, ActionTargetType.AREA): "every ally in reach",
    (ConditionTargetKind.ALLY, ActionTargetType.FILTERED_GROUP): "allies you choose",
    (ConditionTargetKind.ENEMY, ActionTargetType.SINGLE): "an enemy",
    (ConditionTargetKind.ENEMY, ActionTargetType.AREA): "every enemy in reach",
    (ConditionTargetKind.ENEMY, ActionTargetType.FILTERED_GROUP): "enemies you choose",
}

#: Where the technique can land, keyed on ``TechniqueReach``. ``REACH_N`` is
#: rendered separately because it interpolates ``reach_hops``.
_REACH_PHRASES: dict[str, str] = {
    TechniqueReach.SAME: "only where you stand",
    TechniqueReach.ADJACENT: "at your position or one beside it",
    TechniqueReach.ANY: "anywhere in the room",
}


def _join_phrases(phrases: list[str]) -> str:
    """Join names for prose: ``A``, ``A and B``, ``A, B and C``."""
    if not phrases:
        return ""
    if len(phrases) == 1:
        return phrases[0]
    return f"{', '.join(phrases[:-1])} and {phrases[-1]}"


def _target_phrase(relationship: str, target_type: str) -> str:
    """Prose for who the technique lands on."""
    if target_type == ActionTargetType.SELF:
        return _SELF_TARGET_PHRASE
    return _TARGET_PHRASES.get((relationship, target_type), "a target")


def _reach_phrase(reach: str, reach_hops: int) -> str:
    """Prose for how far the technique carries, or ``""`` when it does not travel."""
    if reach == TechniqueReach.REACH_N:
        positions = "position" if reach_hops == 1 else "positions"
        return f"up to {reach_hops} {positions} away"
    return _REACH_PHRASES.get(reach, "")


def _damage_phrase(damage: list[DamageEffectPayload]) -> str:
    """Prose for the technique's damage profiles, or ``""`` when it deals none."""
    if not damage:
        return ""
    named = _join_phrases(sorted({row["damage_type"] for row in damage if row["damage_type"]}))
    kind = f"{named} damage" if named else "damage"
    if any(row["uses_equipped_weapon"] for row in damage):
        return f"Deals {kind} with your equipped weapon."
    return f"Deals {kind}."


def render_technique_effect_sentence(  # noqa: PLR0913
    *,
    relationship: str,
    target_type: str,
    reach: str,
    reach_hops: int,
    arena: str,
    anima_cost: int,
    applies: list[ConditionEffectPayload],
    removes: list[ConditionEffectPayload],
    damage: list[DamageEffectPayload],
    grants: list[CapabilityEffectPayload],
    is_underspecified: bool,
) -> str:
    """Render the plain-words line a player reads on every surface.

    Field names never appear — the player gets "Cast on an ally, anywhere in the
    room, in the physical arena. Costs 5 anima. Applies Guarded." rather than a
    row of enum values. The same sentence renders in the web client, over telnet,
    and in character creation.
    """
    where = _reach_phrase(reach, reach_hops)
    who = _target_phrase(relationship, target_type)
    opening = (
        f"Cast on {who}, {where}, in the {arena} arena."
        if where
        else (f"Cast on {who}, in the {arena} arena.")
    )

    sentences = [opening]
    if anima_cost:
        sentences.append(f"Costs {anima_cost} anima.")

    damage_clause = _damage_phrase(damage)
    if damage_clause:
        sentences.append(damage_clause)
    if applies:
        sentences.append(f"Applies {_join_phrases([row['name'] for row in applies])}.")
    if removes:
        sentences.append(f"Strips {_join_phrases([row['name'] for row in removes])}.")
    if grants:
        sentences.append(f"Grants {_join_phrases([row['name'] for row in grants])}.")

    if is_underspecified:
        sentences.append("Its effects are not yet catalogued.")
    return " ".join(sentences)


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #


def _condition_payload(row: AbstractAppliedCondition) -> ConditionEffectPayload:
    return ConditionEffectPayload(
        name=row.condition.name,
        description=row.condition.player_description or row.condition.description,
        target_kind=row.target_kind,
        minimum_success_level=row.minimum_success_level,
        stack_count=row.stack_count,
    )


def _damage_payload(row: AbstractDamageProfile) -> DamageEffectPayload:
    return DamageEffectPayload(
        damage_type=row.damage_type.name if row.damage_type_id else None,
        base_damage=row.base_damage,
        uses_equipped_weapon=row.uses_equipped_weapon,
        minimum_success_level=row.minimum_success_level,
    )


def _capability_payload(row: AbstractCapabilityGrant) -> CapabilityEffectPayload:
    return CapabilityEffectPayload(
        name=row.capability.name,
        description=row.capability.description,
        base_value=row.base_value,
    )


def technique_is_underspecified(technique: Technique) -> bool:
    """True when nothing about the technique's effect is derivable from authored data.

    No applied condition, no removal, and no damage profile means
    ``derive_target_relationship`` falls all the way through to its SELF default
    without any authored data supporting that answer. 86 of the 272 authored
    techniques were in this state when #2898 was written; making display surface
    the gap is the point, so this is a flag rather than an error.
    """
    return not (
        technique.cached_condition_applications
        or technique.cached_removed_conditions
        or technique.cached_damage_profiles
    )


def technique_relationship_is_ambiguous(technique: Technique) -> bool:
    """True when the technique's payload rows disagree about who it targets.

    ``derive_target_relationship`` must return exactly one relationship, so a
    technique whose applied and removed rows carry more than one distinct
    ``target_kind`` gets an answer that is a guess. The motivating case (found
    while authoring #2764) is a self-teleport that applies Flanked to an enemy: the
    only authored ``target_kind`` is ENEMY, so it derives as enemy-targeted, and it
    looks correct.

    Authored data carries no signal separating "the point of the technique" from
    "a side effect", so this reports the ambiguity instead of guessing again —
    ``derive_target_relationship``'s own answer is deliberately left untouched,
    since it gates live cast targeting.
    """
    kinds = {row.target_kind for row in technique.cached_condition_applications}
    kinds |= {row.target_kind for row in technique.cached_removed_conditions}
    return len(kinds) > 1


def summarize_technique_effects(technique: Technique) -> TechniqueEffectPayload:
    """Build the shared effect summary for *technique*.

    Reads the technique's ``cached_*`` payload lists and the two existing
    derivations. Prefer ``technique.cached_effect_summary`` at call sites — it
    memoizes this on the row.
    """
    applies = [_condition_payload(row) for row in technique.cached_condition_applications]
    removes = [_condition_payload(row) for row in technique.cached_removed_conditions]
    damage = [_damage_payload(row) for row in technique.cached_damage_profiles]
    grants = [_capability_payload(row) for row in technique.cached_capability_grants]

    # str() unwraps the TextChoices member so the payload carries a plain wire value.
    relationship = str(derive_target_relationship(technique))
    is_underspecified = technique_is_underspecified(technique)

    return TechniqueEffectPayload(
        relationship=relationship,
        hostile=is_technique_hostile(technique),
        target_type=technique.target_type,
        reach=technique.reach,
        reach_hops=technique.reach_hops,
        arena=technique.action_category,
        anima_cost=technique.anima_cost,
        applies=applies,
        removes=removes,
        damage=damage,
        grants=grants,
        summary=render_technique_effect_sentence(
            relationship=relationship,
            target_type=technique.target_type,
            reach=technique.reach,
            reach_hops=technique.reach_hops,
            arena=technique.action_category,
            anima_cost=technique.anima_cost,
            applies=applies,
            removes=removes,
            damage=damage,
            grants=grants,
            is_underspecified=is_underspecified,
        ),
        is_underspecified=is_underspecified,
    )


#: The cached_property names that go stale when a technique's payload rows change.
_PAYLOAD_CACHE_ATTRS = (
    "cached_condition_applications",
    "cached_removed_conditions",
    "cached_damage_profiles",
    "cached_capability_grants",
    "cached_effect_summary",
    "is_lock_applying",
)


def invalidate_technique_payload_caches(technique: Technique) -> None:
    """Drop the per-instance payload caches after writing payload rows.

    Techniques are SharedMemoryModels, so an instance that has already answered a
    display or resolution question keeps that answer for the life of the process.
    Every authoring path that adds or removes a payload row calls this so the next
    read rebuilds. Safe to call when nothing was cached.
    """
    for attr in _PAYLOAD_CACHE_ATTRS:
        technique.__dict__.pop(attr, None)


def technique_effect_authoring_gaps() -> list[TechniqueAuthoringGap]:
    """Every authored technique whose effect data cannot be read back with confidence.

    The staff-facing half of #2898: display makes the gaps visible to players as
    "not yet catalogued", and this makes them findable by the people who author
    the content. Surfaced on ``TechniqueAdmin`` as columns and filters; there is
    deliberately no management command (CLAUDE.md) and no CI gate — the missing
    conditions are lore-repo content work, out of this issue's scope.
    """
    techniques = Technique.objects.select_related("gift").prefetch_related(
        # to_attr targets the cached_property names so the derivations below read
        # the prefetched rows rather than re-querying per technique, and so the
        # prefetch can never go stale against the identity map (#2728).
        Prefetch(
            "condition_applications",
            queryset=TechniqueAppliedCondition.objects.select_related("condition"),
            to_attr="cached_condition_applications",
        ),
        Prefetch(
            "removed_conditions",
            queryset=TechniqueRemovedCondition.objects.select_related("condition"),
            to_attr="cached_removed_conditions",
        ),
        Prefetch(
            "damage_profiles",
            queryset=TechniqueDamageProfile.objects.select_related("damage_type"),
            to_attr="cached_damage_profiles",
        ),
    )
    gaps: list[TechniqueAuthoringGap] = []
    for technique in techniques:
        underspecified = technique_is_underspecified(technique)
        ambiguous = technique_relationship_is_ambiguous(technique)
        if not (underspecified or ambiguous):
            continue
        gaps.append(
            TechniqueAuthoringGap(
                technique_id=technique.pk,
                technique_name=technique.name,
                gift_name=technique.gift.name,
                derived_relationship=str(derive_target_relationship(technique)),
                is_underspecified=underspecified,
                relationship_is_ambiguous=ambiguous,
            )
        )
    return gaps
