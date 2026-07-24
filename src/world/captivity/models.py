"""Captivity records (#931).

A ``Captivity`` is the state of one character being held: where (the cell
instance), by whom (the captor org), under what stakes (the off-screen-loss
flag set at the consent gate), and — once it exists — against what ransom.

Shared cells are the default: a party captured together points many
``Captivity`` rows at one ``InstancedRoom``. Separate linked cells off a
shared hallway are a deferred enhancement; nothing here forbids them, since
``cell`` is a plain FK, not one-per-room.

The captive's IC condition lives on ``CharacterSheet.lifecycle_state`` (it
flips to ``CAPTURED`` on capture and back to ``ALIVE`` on resolution). That
state already makes the character read as ``is_inactive`` everywhere, which
is what enforces the umbrella's off-screen-stasis ruling for captives — no
separate AP-freeze field is needed (there is no AP-regen cron to suppress,
and any future one must already skip inactive characters).
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from world.captivity.constants import CaptivityStatus

_MISSION_TEMPLATE_FK = "missions.MissionTemplate"


class Captivity(SharedMemoryModel):
    """One character's imprisonment and how it ends."""

    captive = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="captivities",
        help_text="The held character (the body, regardless of presented persona).",
    )
    cell = models.ForeignKey(
        "instances.InstancedRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="captivities",
        help_text=(
            "The instanced cell this captive is held in (shared by a captured"
            " party). Goes null when the cell is torn down on resolution — a"
            " resolved captivity outlives its cell so its history survives."
            " Also null for Brig-path captures (holding_room is set instead)."
        ),
    )
    holding_room = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="held_captivities",
        help_text=(
            "The persistent room the captive is held in (e.g. a ship's Brig)."
            " Null for instanced-cell captures — set when cell is null."
        ),
    )
    # ObjectDB by design (#2608): raw capture-time `character.location` — no Room
    # typeclass guarantee, so no RoomProfile to point at.
    return_location = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="return_captivities",
        help_text=(
            "Where the captive returns on resolution. Used when cell is null"
            " (Brig path); falls back to cell.return_location for instanced cells."
        ),
    )
    captor_organization = models.ForeignKey(
        "societies.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="captives",
        help_text="The NPC org holding the captive and issuing any ransom demand.",
    )
    status = models.CharField(
        max_length=20,
        choices=CaptivityStatus.choices,
        default=CaptivityStatus.HELD,
    )
    offscreen_loss_allowed = models.BooleanField(
        default=False,
        help_text=(
            "Authored at the consent gate. Intended to gate off-screen loss"
            " (False = un-loseable while the player is away), but NO consumer"
            " reads it yet — escalation/loss logic that honours it is a later"
            " phase. Today it is a recorded intent only.  TODO(#931 followup)."
        ),
    )
    ransom_project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ransom_captivities",
        help_text=(
            "The crowdfundable RANSOM Project standing in the cell (#1500). Anyone may"
            " donate toward it; the instant it's fully funded the captive is freed."
            " The FK lives here (the consumer), keeping the projects app free of any"
            " captivity dependency (ADR-0010)."
        ),
    )
    rescue_template = models.ForeignKey(
        _MISSION_TEMPLATE_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The rescue mission a discovered rescue clue grants (#931 Phase 4). Resolved"
            " from the capture setup (override-then-default) and stamped at capture time."
        ),
    )
    captured_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the captivity ended. Null while HELD.",
    )

    class Meta:
        verbose_name = "Captivity"
        verbose_name_plural = "Captivities"
        ordering = ["-captured_at"]
        constraints = [
            # A character can hold at most one active captivity at a time.
            # Partial unique constraints already create their backing index,
            # so no separate Meta.indexes entry is needed here.
            models.UniqueConstraint(
                fields=["captive"],
                condition=models.Q(status=CaptivityStatus.HELD),
                name="unique_active_captivity_per_captive",
            ),
        ]

    def __str__(self) -> str:
        return f"Captivity({self.captive.character.key}: {self.get_status_display()})"


class CaptivityConfig(SharedMemoryModel):
    """Singleton (pk=1) — the one logical default for the captivity loops (#931 Phase 4).

    Every capture uses these defaults unless the CAPTURE consequence effect carries
    its own overrides (override-then-default), so a marquee captor (an Ariwn dungeon)
    can hand-craft its cell + loops while everything else falls through to one
    authored default. Templates are authored content; a null template means that loop
    simply isn't granted until one is authored. Player-visible text is authored in the
    deployment's own voice — nothing here ships prose.
    """

    objects = ArxSharedMemoryManager()

    captive_template = models.ForeignKey(
        _MISSION_TEMPLATE_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Default mission granted to the captive on capture — its options carry "
            "the escape + get-word-out CHALLENGE loops. Null = no captive loop yet."
        ),
    )
    rescue_template = models.ForeignKey(
        _MISSION_TEMPLATE_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Default rescue mission surfaced to allies at the capture site / cell.",
    )
    cell_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Default cell room name (player-visible — author in your voice).",
    )
    cell_description = models.TextField(
        blank=True,
        default="",
        help_text="Default cell room description (player-visible — author in your voice).",
    )
    clue_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Default rescue-clue name at the capture site (player-visible — your voice).",
    )
    clue_description = models.TextField(
        blank=True,
        default="",
        help_text="Default rescue-clue description (player-visible — author in your voice).",
    )
    clue_detect_difficulty = models.PositiveIntegerField(
        default=0,
        help_text="Default Search-check difficulty to spot the rescue clue. Placeholder.",
    )

    @classmethod
    def load(cls) -> CaptivityConfig:
        """Fetch (or lazily create) the singleton row."""
        obj = cls.objects.cached_singleton()
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self) -> str:
        return "Captivity defaults"
