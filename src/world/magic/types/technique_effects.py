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


class TechniqueFormPayload(TypedDict):
    """One form of a technique that a specific caster can work (#2901).

    #2898's ``TechniqueEffectPayload`` describes the *authored* technique, which
    is the whole story for the two catalog surfaces. A caster who has woven a
    GIFT thread also reaches resonance-specialized forms of the same technique,
    and the base form remains available alongside them (``cast <tech> base``).
    This is one entry in that list.

    Built by ``world.magic.services.technique_forms.available_technique_forms``.
    """

    #: ``TechniqueVariant`` pk, or ``None`` for the base form.
    variant_id: int | None
    #: What the form is called: the variant's ``name_override``, else the
    #: technique's own name.
    name: str
    #: ``Resonance`` pk this form manifests through, or ``None`` for the base
    #: form (which is resonance-agnostic).
    resonance_id: int | None
    #: Display name of that resonance, or ``""`` for the base form. Doubles as
    #: the token a player passes to ``cast <tech> variant=<resonance>``.
    resonance_name: str
    intensity: int
    control: int
    #: True for the form a bare ``cast <tech>`` works right now. Exactly one
    #: entry in a list carries this.
    is_default: bool
    #: True when the caster cannot work this form yet. Locked entries carry the
    #: authored numbers so the deepening reads as a goal, and are omitted from
    #: the in-scene cast list.
    is_locked: bool
    #: Thread level that unlocks this form; 0 for the base form.
    unlock_thread_level: int
    #: The caster's current level on the thread this form resolves through.
    thread_level: int
    effect_summary: TechniqueEffectPayload


class TechniqueSignaturePayload(TypedDict):
    """The signature flourish riding whichever form the caster works (#2901).

    A signature is an ADDITIVE modifier, never a sibling form (ADR-0072), so it
    is a single field beside the form list rather than an entry inside it.
    """

    name: str
    narrative_snippet: str
    intensity_delta: int


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
