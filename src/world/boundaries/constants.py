from django.db import models


class BoundaryKind(models.TextChoices):
    """Enforcement tier of a PlayerBoundary."""

    HARD_LINE = "hard_line", "Hard line"  # auto-blocked, always private
    ADVISORY = "advisory", "Advisory"  # communicated, shareable


class TreasuredSubjectKind(models.TextChoices):
    """What kind of thing a TreasuredSubject names.

    Mirrors `world.stories.constants.StakeSubjectKind` member values VERBATIM
    (same string values) so matching compares raw strings without importing
    stories (`boundaries` must not depend on `stories` — ADR-0010 FK
    direction specific->general).
    """

    PERSONAL_JEOPARDY = "personal_jeopardy", "Personal jeopardy"
    NPC_FATE = "npc_fate", "NPC fate"
    LOCATION = "location", "Location"
    FACTION = "faction", "Faction relationship"
    ITEM = "item", "Item"
    CAMPAIGN_TRACK = "campaign_track", "Campaign track"
    ASSET = "asset", "Asset"
    CUSTOM = "custom", "Custom (trust-gated)"
