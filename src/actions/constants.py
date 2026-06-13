"""Constants for the action system."""

from enum import StrEnum

from django.db import models


class EnhancementSourceType(models.TextChoices):
    """The type of model that provides an ActionEnhancement."""

    DISTINCTION = "distinction", "Distinction"
    CONDITION = "condition", "Condition"
    TECHNIQUE = "technique", "Technique"


class TransformType(models.TextChoices):
    """Named transforms for kwarg modification."""

    UPPERCASE = "uppercase", "Uppercase"
    LOWERCASE = "lowercase", "Lowercase"


class Pipeline(models.TextChoices):
    """Resolution pattern for ActionTemplate."""

    SINGLE = "single", "Single Check"
    GATED = "gated", "Gated (with prerequisite checks)"


class GateRole(models.TextChoices):
    """Semantic role of an ActionTemplateGate."""

    ACTIVATION = "activation", "Activation"


class ActionTargetType(models.TextChoices):
    """Target type for data-driven ActionTemplates (mirrors TargetType StrEnum)."""

    SELF = "self", "Self"
    SINGLE = "single", "Single Target"
    AREA = "area", "Area"
    FILTERED_GROUP = "filtered_group", "Filtered Group"


class TargetKind(models.TextChoices):
    """Entity-type axis for action targeting.

    Orthogonal to ActionTargetType (cardinality). Kind = what type of entity
    the action targets; cardinality = how many / how they're selected.
    """

    PERSONA = "persona", "Persona"
    CHARACTER = "character", "Character"
    ITEM = "item", "Item"
    ROOM = "room", "Room"


class ActionBackend(models.TextChoices):
    """Which backend system resolves a PlayerAction."""

    CHALLENGE = "challenge", "Challenge"
    COMBAT = "combat", "Combat"
    REGISTRY = "registry", "Registry"


class ActionCategory(models.TextChoices):
    """Physical/social/mental arena for any action (magical or not).

    The single canonical axis: techniques classify into it, combat actions
    carry it (focused/attack category), and fatigue pools key off it. Climbing
    a wall is physical, flirting is social, a feat of memory is mental.
    """

    PHYSICAL = "physical", "Physical"
    SOCIAL = "social", "Social"
    MENTAL = "mental", "Mental"


class CombatActionSlot(models.TextChoices):
    """Which combat round-action slot a declared COMBAT technique fills.

    ``FOCUSED`` is the actor's single primary action; the passive slots carry
    auto-running techniques per arena. Values intentionally match the frontend
    ``ActionSlot`` strings so the wire round-trips without translation.
    """

    FOCUSED = "focused", "Focused"
    PASSIVE_PHYSICAL = "passive-physical", "Passive (Physical)"
    PASSIVE_SOCIAL = "passive-social", "Passive (Social)"
    PASSIVE_MENTAL = "passive-mental", "Passive (Mental)"


class PlayerDecision(StrEnum):
    """Player decisions for paused resolution pipelines."""

    CONFIRM = "confirm"
    ABORT = "abort"
    REROLL = "reroll"


class ResolutionPhase(StrEnum):
    """Phase of the action resolution state machine.

    StrEnum (not TextChoices) because this is in-memory state machine state,
    never stored in a database column.
    """

    GATE_PENDING = "gate_pending"
    GATE_RESOLVED = "gate_resolved"
    MAIN_PENDING = "main_pending"
    MAIN_RESOLVED = "main_resolved"
    CONTEXT_PENDING = "context_pending"
    COMPLETE = "complete"
