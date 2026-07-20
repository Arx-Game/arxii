from django.db import models


class NarrativeCategory(models.TextChoices):
    STORY = "story", "Story update"
    ATMOSPHERE = "atmosphere", "Atmosphere"
    VISIONS = "visions", "Visions"
    HAPPENSTANCE = "happenstance", "Happenstance"
    SYSTEM = "system", "System"
    COVENANT = "covenant", "Covenant"
    RENOWN = "renown", "Renown"
    WEATHER = "weather", "Weather"
    ABILITY = "ability", "Ability access"


class GemitReach(models.TextChoices):
    """How wide a gemit broadcasts (#1450) — its audience scope.

    GAME_WIDE reaches every online session (the classic gemit). SPECIFIED reaches the members of any
    combination of the linked societies and/or organizations — the two are not mutually exclusive,
    so one gemit can target a House (org) and a Society together.
    """

    GAME_WIDE = "game_wide", "Game-wide"
    SPECIFIED = "specified", "Specified"


class ConditionType(models.TextChoices):
    """Which fields on an AmbientEmoteCondition are active (#2471 v2).

    Each value compiles to one DSL filter leaf — see
    world.narrative.ambient_content.compile_line_filter. SPECIES compiles to a plain ``==``
    on the character's species name (no new DSL op needed); the other three back new
    Character methods (has_resonance_at_least / has_public_distinction / fame_tier_at_least)
    via the same method-dispatch pattern has_property/has_capability/shares_covenant_with
    already use.
    """

    SPECIES = "species", "Species"
    RESONANCE_MIN = "resonance_min", "Resonance threshold"
    DISTINCTION = "distinction", "Distinction"
    RENOWN_MIN = "renown_min", "Fame tier"
    LEGEND_DEED = "legend_deed", "Has common-knowledge deeds"


class ConditionConnector(models.TextChoices):
    """How an AmbientEmoteLine's conditions combine (#2471 v2).

    Flat list only — a line's conditions are ALL joined by one connector, no nested
    AND-of-ORs. Arbitrary nesting is explicitly deferred (needs an authoring form/tool
    first) — see the #2471 spec's Scope / follow-ups.
    """

    AND = "and", "All conditions"
    OR = "or", "Any condition"
