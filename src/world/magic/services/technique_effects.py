"""Derived effect summary for a Technique — the one thing every surface shows (#2898).

A technique's ``Technique`` row carries almost no differentiation; everything that
tells one technique from another lives in five sibling tables
(``TechniqueCapabilityGrant`` / ``TechniqueAppliedCondition`` /
``TechniqueDamageProfile`` / ``TechniqueRemovedCondition`` /
``TechniqueTreatment``) that no display surface ever read. This module reads them
once and renders them, both as structured data and as a plain-words line.
``TechniqueTreatment`` joined in #3682 — it was the one payload family #2898
missed, so a treatment-only technique described itself as having no effect.

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

from django.core.cache import cache
from django.db.models import Prefetch

from actions.constants import ActionTargetType
from world.magic.constants import TechniqueReach
from world.magic.models.techniques import (
    ConditionTargetKind,
    Technique,
    TechniqueAppliedCondition,
    TechniqueCapabilityGrant,
    TechniqueDamageProfile,
    TechniqueRemovedCondition,
    TechniqueTreatment,
)
from world.magic.services.hostility import is_technique_hostile
from world.magic.services.targeting import derive_target_relationship
from world.magic.types.technique_effects import (
    CapabilityEffectPayload,
    ConditionEffectPayload,
    DamageEffectPayload,
    TechniqueAuthoringGap,
    TechniqueEffectPayload,
    TreatmentEffectPayload,
)

if TYPE_CHECKING:
    from world.magic.models.techniques import (
        AbstractAppliedCondition,
        AbstractCapabilityGrant,
        AbstractDamageProfile,
    )
    from world.magic.specialization.services import _ResolvedTechnique

    #: What the summariser accepts: an authored ``Technique`` row, or a resolved
    #: *form* of one. Both answer the same ``cached_<payload>`` reads (#2901) —
    #: ``_ResolvedTechnique`` aliases them onto the variant's payload.
    SummarizableTechnique = Technique | _ResolvedTechnique


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
    treatments: list[TreatmentEffectPayload],
    grants: list[CapabilityEffectPayload],
    is_underspecified: bool,
) -> str:
    """Render the plain-words line a player reads on every surface.

    Field names never appear — the player gets "Cast on an ally, anywhere in the
    room, in the physical arena. Costs 5 anima. Applies Guarded." rather than a
    row of enum values. The same sentence renders in the web client, over telnet,
    and in character creation.

    Capability grants read as "Knowing it grants X", never as something the cast
    does: a grant is standing possession and the cast deliberately does nothing
    with it (ADR-0248). Before #3682 they sat unqualified among the cast clauses,
    which told the player a lie about when the capability arrives.
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
    if treatments:
        sentences.append(f"Treats {_join_phrases(sorted({row['treats'] for row in treatments}))}.")
    if grants:
        sentences.append(f"Knowing it grants {_join_phrases([row['name'] for row in grants])}.")

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


def _treatment_payload(row: TechniqueTreatment) -> TreatmentEffectPayload:
    template = row.treatment_template
    return TreatmentEffectPayload(
        name=template.name,
        description=template.description,
        treats=template.target_condition.name,
        target_kind=row.target_kind,
        minimum_success_level=row.minimum_success_level,
    )


def _capability_payload(row: AbstractCapabilityGrant) -> CapabilityEffectPayload:
    return CapabilityEffectPayload(
        name=row.capability.name,
        description=row.capability.description,
        base_value=row.base_value,
    )


def technique_payload_prefetches(*, prefix: str = "") -> list[Prefetch]:
    """The five payload prefetches any queryset feeding the effect summary needs.

    ``summarize_technique_effects`` reads five sibling tables, so a surface that
    builds a summary per row in a list — the in-scene cast list, the character
    sheet's magic section, the ``TechniqueAdmin`` changelist — pays five queries
    per technique unless it prefetches them. Each ``to_attr`` is the
    ``cached_*`` property name the derivations read, which is also what keeps a
    prefetched row from going stale against the identity map (#2728, ADR-0263).

    One definition rather than one per call site (#3682): the set has to stay in
    lockstep with what the summary reads, and it did not — treatments were added
    to the summary and three separately-maintained copies of this block each had
    to be found and updated. The next payload family should need one edit.

    ``prefix`` is the relation path from the queryset's model to the Technique
    (``"technique__"`` when starting from ``CharacterTechnique``, empty when
    starting from ``Technique`` itself).
    """
    return [
        Prefetch(
            f"{prefix}condition_applications",
            queryset=TechniqueAppliedCondition.objects.select_related("condition"),
            to_attr="cached_condition_applications",
        ),
        Prefetch(
            f"{prefix}removed_conditions",
            queryset=TechniqueRemovedCondition.objects.select_related("condition"),
            to_attr="cached_removed_conditions",
        ),
        Prefetch(
            f"{prefix}damage_profiles",
            queryset=TechniqueDamageProfile.objects.select_related("damage_type"),
            to_attr="cached_damage_profiles",
        ),
        Prefetch(
            f"{prefix}treatments",
            queryset=TechniqueTreatment.objects.select_related(
                "treatment_template__target_condition"
            ),
            to_attr="cached_treatments",
        ),
        Prefetch(
            f"{prefix}capability_grants",
            queryset=TechniqueCapabilityGrant.objects.select_related("capability"),
            to_attr="cached_capability_grants",
        ),
    ]


def technique_is_underspecified(technique: SummarizableTechnique) -> bool:
    """True when nothing about the technique's effect is derivable from authored data.

    No applied condition, no removal, no damage profile and no treatment means
    ``derive_target_relationship`` falls all the way through to its SELF default
    without any authored data supporting that answer. 86 of the 272 authored
    techniques were in this state when #2898 was written; making display surface
    the gap is the point, so this is a flag rather than an error.

    Treatments joined the check in #3682: they were authorable from #2668 and
    carry their own ``target_kind``, so a technique whose only payload is a
    treatment *is* specified — the old check called it blank and display told
    the player its effects were not catalogued.

    Capability grants are deliberately still excluded. A grant means standing
    possession (ADR-0248) and the cast does nothing with it, so a grant-only
    technique really does have no derivable cast effect.
    """
    return not (
        technique.cached_condition_applications
        or technique.cached_removed_conditions
        or technique.cached_damage_profiles
        or technique.cached_treatments
    )


def technique_is_not_castable_standalone(technique: SummarizableTechnique) -> bool:
    """True when the technique carries no ``action_template`` (#3682).

    ``request_technique_cast`` rejects such a technique ("not castable
    standalone") and ``castable_technique_links_for_sheet`` filters it out of
    both the web and telnet cast lists — but ``get_technique_options`` still
    offers it as a valid CG pick and ``compute_magic_errors`` still accepts it,
    so a player can spend a pick on something that never appears in their cast
    interface. Every one of the 306 authored techniques was in this state when
    this was written.

    This reports the linkage's state; it does not judge it. Whether a technique
    is *meant* to be castable — as opposed to carrying only standing capability
    value — is an authoring decision, and no readiness policy is enforced here.
    """
    return not technique.action_template_id


def technique_relationship_is_ambiguous(technique: SummarizableTechnique) -> bool:
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

    Treatment rows carry a ``target_kind`` too and now count (#3682), so an
    ALLY-healing technique that also debuffs an enemy reads as the guess it is.
    """
    kinds = {row.target_kind for row in technique.cached_condition_applications}
    kinds |= {row.target_kind for row in technique.cached_removed_conditions}
    kinds |= {row.target_kind for row in technique.cached_treatments}
    return len(kinds) > 1


def summarize_technique_effects(technique: SummarizableTechnique) -> TechniqueEffectPayload:
    """Build the shared effect summary for *technique*.

    Reads the technique's ``cached_*`` payload lists and the two existing
    derivations. Prefer ``technique.cached_effect_summary`` at call sites — it
    memoizes this on the row.
    """
    applies = [_condition_payload(row) for row in technique.cached_condition_applications]
    removes = [_condition_payload(row) for row in technique.cached_removed_conditions]
    damage = [_damage_payload(row) for row in technique.cached_damage_profiles]
    treatments = [_treatment_payload(row) for row in technique.cached_treatments]
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
        treatments=treatments,
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
            treatments=treatments,
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
    "cached_treatments",
    "cached_capability_grants",
    "cached_effect_summary",
    "is_lock_applying",
)


#: Cross-process cache key holding the technique catalog's revision counter.
#: Read by the tuning panels, which cache a whole-catalog evaluation for 24h and
#: had no way to notice an edit (#3682).
TECHNIQUE_CATALOG_REVISION_KEY = "magic:technique-catalog-revision"


def technique_catalog_revision() -> int:
    """The technique catalog's current revision number (#3682).

    A monotonically rising counter bumped by every authoring write, for keying
    caches that summarise the catalog as a whole rather than one row. Starts at
    0; a cache eviction resets it, which costs a recomputation and never serves
    stale data, because the key changes either way.
    """
    return cache.get(TECHNIQUE_CATALOG_REVISION_KEY) or 0


def bump_technique_catalog_revision() -> None:
    """Advance the catalog revision so whole-catalog caches miss (#3682).

    ``cache.incr`` raises when the key is absent, so seed it with ``cache.add``
    first — ``add`` is a no-op when another process already seeded it, which
    keeps two concurrent authoring saves from resetting each other to 1.
    """
    cache.add(TECHNIQUE_CATALOG_REVISION_KEY, 0, None)
    try:
        cache.incr(TECHNIQUE_CATALOG_REVISION_KEY)
    except ValueError:
        # The key expired between the add and the incr. Losing a bump here would
        # serve a stale panel, so re-seed at 1 rather than swallowing it.
        cache.set(TECHNIQUE_CATALOG_REVISION_KEY, 1, None)


def invalidate_technique_payload_caches(technique: Technique) -> None:
    """Drop the per-instance payload caches after writing payload rows.

    Techniques are SharedMemoryModels, so an instance that has already answered a
    display or resolution question keeps that answer for the life of the process.
    Every authoring path that adds or removes a payload row calls this so the next
    read rebuilds. Safe to call when nothing was cached.

    Also bumps the catalog revision (#3682). This is the one seam every authoring
    write already passes through, and the tuning panels' 24h whole-catalog caches
    were keyed on their numeric parameters alone: re-submitting the same
    parameters after an edit returned the pre-edit corpus, so the numbers staff
    were tuning against were the ones they had just changed.
    """
    for attr in _PAYLOAD_CACHE_ATTRS:
        technique.__dict__.pop(attr, None)
    bump_technique_catalog_revision()


#: The cached_property names that go stale when a variant's payload rows change.
#: A variant has no ``removed_conditions`` relation (no
#: ``TechniqueVariantRemovedCondition`` model) and no ``is_lock_applying``, so
#: this is deliberately shorter than ``_PAYLOAD_CACHE_ATTRS``.
_VARIANT_PAYLOAD_CACHE_ATTRS = (
    "cached_condition_applications",
    "cached_damage_profiles",
    "cached_capability_grants",
    "cached_effect_summary",
)


def invalidate_variant_payload_caches(variant) -> None:
    """Drop the per-instance payload caches on a ``TechniqueVariant`` (#2901).

    The variant sibling of :func:`invalidate_technique_payload_caches`. Variants
    are SharedMemoryModels too, so a variant that has already answered the form
    list keeps that answer for the life of the process. Safe to call when
    nothing was cached.

    A variant's summary is built from its parent's scalar fields as well as its
    own payload, so editing the *parent* invalidates the variant too: call this
    for each of ``technique.cached_variants`` after
    :func:`invalidate_technique_payload_caches`.
    """
    for attr in _VARIANT_PAYLOAD_CACHE_ATTRS:
        variant.__dict__.pop(attr, None)


def technique_effect_authoring_gaps() -> list[TechniqueAuthoringGap]:
    """Every authored technique whose effect data cannot be read back with confidence.

    The staff-facing half of #2898: display makes the gaps visible to players as
    "not yet catalogued", and this makes them findable by the people who author
    the content. Surfaced on ``TechniqueAdmin`` as columns and filters; there is
    deliberately no management command (CLAUDE.md) and no CI gate — the missing
    conditions are content work, out of this issue's scope.

    Missing cast linkage is reported separately (see
    ``technique_is_not_castable_standalone``) rather than being folded in here —
    every authored technique lacks a template today, so membership would become
    meaningless.
    """
    techniques = Technique.objects.select_related("gift").prefetch_related(
        # to_attr targets the cached_property names so the derivations below read
        # the prefetched rows rather than re-querying per technique, and so the
        # prefetch can never go stale against the identity map (#2728).
        *technique_payload_prefetches(),
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
