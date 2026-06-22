"""Character Secrets (#1334) — hidden facts about a concrete entity.

A ``Secret`` is the missing fourth primitive alongside Distinction (permanent trait) /
Condition (live state) / Resonance: a hidden FACT or RELATIONSHIP that must be earned and
shared, carrying consequences. Bio/story stay public; sensitive information lives here.

This module owns the secret *content* (slice 1). Discovery + the per-knower held record
(partial knowledge), the clue-target wiring, and the display tab are later slices.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.secrets.constants import SecretLevel, SecretProvenance


class SecretCategory(SharedMemoryModel):
    """What a secret is *about* — gossip, scandal, magical, family, incriminating, …

    A staff-editable lookup (not ``TextChoices``) so the taxonomy can grow without a
    migration. A secret with no category reads as **Unknown** — a first-class state, not a
    gap: a knower may hold the fact without having placed its category.
    """

    name = models.CharField(
        max_length=60, unique=True, help_text="Category label (player-visible)."
    )
    description = models.TextField(blank=True, help_text="Staff note on what belongs here.")
    is_active = models.BooleanField(default=True, help_text="Offer this category to authors.")

    class Meta:
        verbose_name = "Secret category"
        verbose_name_plural = "Secret categories"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Secret(SharedMemoryModel):
    """A hidden fact about a character, with a level, a category, and consequences.

    Subject-anchored and **always single-owner**: ``subject_sheet`` is who the secret is *about*
    and owns it (authorship ≠ ownership — a GM-written secret *for* a character is owned by that
    character, who knows it; others discover it). There are no group/shared secrets: a multi-party
    situation (affair, blackmail) is two *distinct* secrets, one owned by each character — never a
    shared row. ``category`` and ``consequences`` may be left blank/null to mean **Unknown** (a
    deliberate puzzle state).

    Provenance + the anchor-scales-with-level invariant (``clean``) keep player-flavor from
    masquerading as canon: only Level-1 player-flavor secrets may be free-authored; anything
    heavier must be GM- or action-anchored.
    """

    subject_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="secrets",
        help_text="The character this secret is about — and its sole owner.",
    )
    level = models.PositiveSmallIntegerField(
        choices=SecretLevel.choices,
        default=SecretLevel.UNCOMMON_KNOWLEDGE,
        help_text="How deep/dangerous — narrative weight + default share-scope.",
    )
    category = models.ForeignKey(
        SecretCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="secrets",
        help_text="What the secret is about. Null = Unknown (not yet placed).",
    )
    consequences = models.TextField(
        blank=True,
        help_text="What happens if it surfaces. Blank = Unknown.",
    )
    content = models.TextField(
        blank=True,
        help_text="The secret itself, as narrated. Player- or GM-authored prose.",
    )
    provenance = models.CharField(
        max_length=10,
        choices=SecretProvenance.choices,
        help_text="Where the secret came from (drives the anchor rule + OOC attribution).",
    )
    author_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="authored_secrets",
        help_text="The narrating persona (player-authored). Null for GM/staff-authored.",
    )
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_date"]
        indexes = [
            models.Index(fields=["subject_sheet", "level"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_level_display()} secret about {self.subject_sheet_id}"

    def clean(self) -> None:
        """Enforce anchor-scales-with-level: free player-flavor only at Level 1 (#1334).

        Player-flavor secrets carry no mechanical effect, so their truth is moot — but that
        only holds at Level 1. Anything heavier must be GM- or action-anchored, which is what
        stops a player from free-writing a Dangerous-tier "I killed a god."
        """
        super().clean()
        if (
            self.provenance == SecretProvenance.PLAYER_FLAVOR
            and self.level != SecretLevel.UNCOMMON_KNOWLEDGE
        ):
            msg = "Player-authored secrets above Level 1 must be GM- or action-anchored."
            raise ValidationError({"level": msg})


class SecretKnowledge(SharedMemoryModel):
    """A character's held knowledge of a secret, with partial-knowledge layers (#1334).

    Roster-scoped like ``CharacterClue`` (knowledge follows the character across players).
    Holding the row means you know the **fact**; ``knows_category`` / ``knows_consequences``
    track whether you've *also* placed its category or learned its fallout — so a secret's
    Unknown layers can persist per-knower even after the fact itself is out. Layers only ever
    unlock (monotonic); they're never re-hidden.
    """

    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="secrets_known",
        help_text="The character who holds this knowledge.",
    )
    secret = models.ForeignKey(
        Secret,
        on_delete=models.CASCADE,
        related_name="known_by",
        help_text="The secret this character knows.",
    )
    knows_category = models.BooleanField(
        default=False,
        help_text="Whether this knower has placed the secret's category (else it reads Unknown).",
    )
    knows_consequences = models.BooleanField(
        default=False,
        help_text="Whether this knower has learned the secret's consequences.",
    )
    found_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["roster_entry", "secret"]
        ordering = ["-found_at"]
        verbose_name = "Secret knowledge"
        verbose_name_plural = "Secret knowledge"

    def __str__(self) -> str:
        return f"{self.roster_entry_id} knows secret {self.secret_id}"
