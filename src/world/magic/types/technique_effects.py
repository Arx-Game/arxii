"""Shared technique-effect summary shapes (#2898).

Four display surfaces used to describe a technique four different ways — CG, the
magic API, the in-scene cast list, and the character sheet — and none of them
reached past the ``Technique`` row into the four payload tables that actually
distinguish one technique from another. These declarations are the single shape
all four now share.

TypedDicts rather than dataclasses for the payload family: every consumer is a
wire surface (the four serializers plus the character-sheet magic section, which
is itself a TypedDict payload read by both the web Magic tab and telnet), which
is the case django_notes.md's "avoid dict returns" rule explicitly admits.
``TechniqueAuthoringGap`` is not a wire surface — it feeds the staff-facing
authoring audit — so it stays a frozen dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


class ConditionEffectPayload(TypedDict):
    """One condition a technique applies to, or strips from, its target."""

    name: str
    description: str
    #: ``ConditionTargetKind`` value — who this particular row lands on.
    target_kind: str
    minimum_success_level: int
    stack_count: int


class DamageEffectPayload(TypedDict):
    """One damage profile a technique resolves on a hit."""

    #: ``DamageType.name``, or ``None`` for untyped damage.
    damage_type: str | None
    base_damage: int
    uses_equipped_weapon: bool
    minimum_success_level: int


class CapabilityEffectPayload(TypedDict):
    """One Capability a technique grants while it is up."""

    name: str
    description: str
    base_value: int


class TechniqueEffectPayload(TypedDict):
    """Everything a player needs to know about what a technique does.

    Built by ``world.magic.services.technique_effects.summarize_technique_effects``
    and cached on the ``Technique`` row (``Technique.cached_effect_summary``), so a
    technique fetched by pk answers every display surface from the identity map
    after the first build.
    """

    #: ``ConditionTargetKind`` value from the existing ``derive_target_relationship``.
    relationship: str
    hostile: bool
    #: ``ActionTargetType`` value (cardinality).
    target_type: str
    #: ``TechniqueReach`` value.
    reach: str
    reach_hops: int
    #: ``ActionCategory`` value (physical / social / mental).
    arena: str
    anima_cost: int
    applies: list[ConditionEffectPayload]
    removes: list[ConditionEffectPayload]
    damage: list[DamageEffectPayload]
    grants: list[CapabilityEffectPayload]
    #: The plain-words line — the same sentence on the web and over telnet.
    summary: str
    #: True when no condition, removal, or damage profile is authored, so nothing
    #: about this technique's effect (including its relationship) is derivable.
    #: Display surfaces render this as "not yet catalogued", never as a blank.
    is_underspecified: bool


@dataclass(frozen=True)
class TechniqueAuthoringGap:
    """One technique whose authored payload cannot be read back with confidence.

    Two independent gaps, either of which can be set:

    ``is_underspecified``
        No applied condition, no removal, no damage profile — the technique's
        relationship is not derivable at all and display has nothing to show.

    ``relationship_is_ambiguous``
        The applied + removed rows carry more than one distinct ``target_kind``,
        so the single derived relationship is a guess. This is the failure mode
        found while authoring #2764: a self-teleport that applies Flanked to an
        enemy derives as enemy-targeted, silently, and looks correct.
    """

    technique_id: int
    technique_name: str
    gift_name: str
    derived_relationship: str
    is_underspecified: bool
    relationship_is_ambiguous: bool
