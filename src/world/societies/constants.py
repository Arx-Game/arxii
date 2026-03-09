"""Constants for the societies system."""

from django.db import models


class LegendSourceCategory(models.TextChoices):
    COMBAT = "combat", "Combat"
    STORY_COMPLETION = "story_completion", "Story Completion"
    CODEX_DISCOVERY = "codex_discovery", "Codex Discovery"
    AUDERE = "audere", "Audere"
    AUDERE_MAJORA = "audere_majora", "Audere Majora"
    TITLE_GAINED = "title_gained", "Title Gained"
    MANTLE_GAINED = "mantle_gained", "Mantle Gained"
    MANTLE_LEVELED = "mantle_leveled", "Mantle Leveled"
    ITEM_PROVENANCE = "item_provenance", "Item Provenance"
    ORGANIZATION_DEED = "organization_deed", "Organization Deed"
    MISSION = "mission", "Mission"
    FIRST_DISCOVERY = "first_discovery", "First Discovery"
    OTHER = "other", "Other"
