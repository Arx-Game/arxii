"""Clue models (#1144) — the Investigation & Discovery pointer.

A ``Clue`` points at exactly one target worth discovering (a codex entry, a mission,
later a secret/scandal). It never exists without a target — no red herrings, no empty
clues — and the target drives the "you already know this" flag when a clue would
surface. *How* a clue is acquired (room search, triggers, random) and *how* it resolves
(automatic grant vs. a research project) are separate layers that link to this pointer;
this module owns only the pointer and the per-character held-clue record.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.mixins import DiscriminatorMixin
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.clues.constants import ClueResolution, ClueTargetKind


class Clue(NaturalKeyMixin, DiscriminatorMixin, SharedMemoryModel):
    """A pointer to one discoverable target. Always points at something (invariant).

    Add a new target kind by adding the value to ``ClueTargetKind``, a nullable
    per-kind FK below, and a ``DISCRIMINATOR_MAP`` entry (SCANDAL planned, #1143).

    Carries a natural key (``slug``, #2451) so grid bundles can reference a clue
    by stable name when authoring a ``RoomClue``/``ClueTrigger`` placement —
    mirrors ``PortalAnchorKind``'s ``name``-keyed natural key.
    """

    DISCRIMINATOR_FIELD = "target_kind"
    DISCRIMINATOR_MAP = {
        ClueTargetKind.CODEX: "target_codex_entry",
        ClueTargetKind.MISSION: "target_mission",
        ClueTargetKind.RESCUE: "target_captivity",
        ClueTargetKind.SECRET: "target_secret",
        # PERSONA_LINK is a documented multi-discriminator exception (#2120): it
        # needs BOTH target_persona AND target_persona_linked set together. The
        # map only tracks target_persona (the primary discriminator target);
        # clean() below folds in the second FK's requirement, per
        # DiscriminatorMixin's own multi-discriminator override guidance.
        ClueTargetKind.PERSONA_LINK: "target_persona",
    }

    slug = models.SlugField(
        max_length=200,
        blank=True,
        null=True,
        unique=True,
        help_text="Stable content-pipeline identifier (#2451). NULL for ad hoc/test clues.",
    )

    target_kind = models.CharField(
        max_length=20,
        choices=ClueTargetKind.choices,
        help_text="Which target this clue points at (selects the active FK).",
    )
    target_codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="clues",
        help_text="The codex entry this clue hints at (target_kind=CODEX).",
    )
    target_mission = models.ForeignKey(
        "missions.MissionTemplate",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="clues",
        help_text="The mission this clue points to (target_kind=MISSION).",
    )
    target_captivity = models.ForeignKey(
        "captivity.Captivity",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="rescue_clues",
        help_text="The captivity this clue points to freeing (target_kind=RESCUE, #931).",
    )
    target_secret = models.ForeignKey(
        "secrets.Secret",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="clues",
        help_text="The character secret this clue points to (target_kind=SECRET, #1334).",
    )
    target_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text=(
            "One side of the masked-identity pair this clue pierces "
            "(target_kind=PERSONA_LINK, #2120). Paired with target_persona_linked -- "
            "both must be set together, see clean(). Per ADR-0010 clues depends on "
            "the scenes primitive, never the reverse."
        ),
    )
    target_persona_linked = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text=(
            "The other side of the masked-identity pair this clue pierces "
            "(target_kind=PERSONA_LINK, #2120). See target_persona."
        ),
    )

    name = models.CharField(
        max_length=200,
        help_text="Name of the clue (e.g. 'Torn Journal Page'). Player-visible.",
    )
    description = models.TextField(
        help_text="What the player sees when they find this clue. Player-visible.",
    )
    research_value = models.PositiveIntegerField(
        default=1,
        help_text="Progress this clue contributes toward resolving its target.",
    )
    resolution_mode = models.CharField(
        max_length=20,
        choices=ClueResolution.choices,
        default=ClueResolution.AUTOMATIC,
        help_text="How holding this clue becomes having the target.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["slug"]

    class Meta:
        ordering = ["name"]
        verbose_name = "Clue"
        verbose_name_plural = "Clues"

    def clean(self) -> None:
        super().clean()
        errors = self._validate_discriminator(self.DISCRIMINATOR_FIELD, self.DISCRIMINATOR_MAP)
        # PERSONA_LINK multi-discriminator exception (#2120) -- see DISCRIMINATOR_MAP's
        # comment above. target_persona is already validated by _validate_discriminator;
        # fold in the matching requirement for target_persona_linked here.
        if self.target_kind == ClueTargetKind.PERSONA_LINK:
            if self._is_unset(self.target_persona_linked_id):
                errors["target_persona_linked"] = "Required when target_kind is persona_link."
        elif not self._is_unset(self.target_persona_linked_id):
            errors["target_persona_linked"] = "Must be null when target_kind is not persona_link."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.name} -> {self.get_active_target_name()}"


class CharacterClue(SharedMemoryModel):
    """A clue a character has acquired (the held-clue record).

    Roster-scoped like codex knowledge: a clue belongs to the character itself, so a
    new player inheriting the character inherits the clues it has found.
    """

    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="clues_held",
    )
    clue = models.ForeignKey(
        Clue,
        on_delete=models.CASCADE,
        related_name="held_by",
    )
    found_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["roster_entry", "clue"]
        ordering = ["-found_at"]
        verbose_name = "Character Clue"
        verbose_name_plural = "Character Clues"

    def __str__(self) -> str:
        return f"{self.roster_entry}: {self.clue.name}"


class ResearchProjectDetails(SharedMemoryModel):
    """Per-kind details for a RESEARCH ``Project`` (#1146): the clue being researched.

    The Project framework keeps per-kind data in a separate model with a OneToOne back
    to the Project (the BUILDING_CONSTRUCTION analogue). On completion the RESEARCH
    handler grants this clue's target to everyone who contributed.
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="research_details",
    )
    clue = models.ForeignKey(
        Clue,
        on_delete=models.CASCADE,
        related_name="research_projects",
        help_text="The clue whose target this project researches toward.",
    )

    class Meta:
        verbose_name = "Research Project Details"
        verbose_name_plural = "Research Project Details"

    def __str__(self) -> str:
        return f"Research<{self.clue.name}> (project #{self.project_id})"


class RoomClue(SharedMemoryModel):
    """A clue hidden in a room, found via a Search check (#1154).

    Mirrors ``room_features.Trap``: room-anchored, with an authored detect difficulty;
    a room may hold several. The Search action rolls against ``detect_difficulty`` to
    surface it; which clues are placed where and how hard they are is staff-editable
    data (placeholder magnitudes deferred to a later author pass per #1143).
    """

    room_profile = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        related_name="hidden_clues",
    )
    clue = models.ForeignKey(
        Clue,
        on_delete=models.CASCADE,
        related_name="room_placements",
    )
    detect_difficulty = models.PositiveIntegerField(
        default=0,
        help_text="Search-check target difficulty to spot this clue here. Placeholder.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this clue is currently findable in the room.",
    )
    eligibility_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Predicate rule gating WHO may discover this placement (identity / org / "
            "resonance / species, evaluated via world.predicates). Empty {} = open to "
            "anyone — the default; add a rule to restrict. Same shape as "
            "MissionTemplate.visibility_rule."
        ),
    )
    fixture_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        help_text=(
            "Permanent stable identifier for authored (exported) clue placements, e.g. "
            "'arx-city/golden-hart-taproom/torn-letter' (#2451). Set when the placement "
            "is authored via the world-builder canvas; NULL for ad hoc/test rows."
        ),
    )

    class Meta:
        ordering = ["room_profile", "clue"]
        verbose_name = "Room Clue"
        verbose_name_plural = "Room Clues"
        constraints = [
            models.UniqueConstraint(
                fields=["room_profile", "clue"],
                name="room_clue_unique_room_clue",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.clue.name} hidden in {self.room_profile}"


class ClueTrigger(SharedMemoryModel):
    """A clue granted passively on entering a room — no search, just a precondition (#1160).

    The trigger counterpart to ``RoomClue``: where a RoomClue is found by an active Search
    check, a ClueTrigger fires on room entry for any eligible character who has not already
    held it (the world reveals it because of who you are / where you are). A room may hold
    several. Which clues trigger where, and the eligibility predicate, are staff-editable
    data (placeholder magnitudes deferred to a later author pass per #1143).
    """

    room_profile = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        related_name="clue_triggers",
    )
    clue = models.ForeignKey(
        Clue,
        on_delete=models.CASCADE,
        related_name="trigger_placements",
    )
    eligibility_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Predicate precondition for the passive grant (identity / resonance / org, via "
            "world.predicates). Empty {} = fires for anyone who enters. Same shape as "
            "RoomClue.eligibility_rule."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this trigger currently fires on entry.",
    )
    fixture_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        help_text=(
            "Permanent stable identifier for authored (exported) clue trigger placements, "
            "e.g. 'arx-city/golden-hart-taproom/torn-letter' (#2451). Set when the placement "
            "is authored via the world-builder canvas; NULL for ad hoc/test rows."
        ),
    )

    class Meta:
        ordering = ["room_profile", "clue"]
        verbose_name = "Clue Trigger"
        verbose_name_plural = "Clue Triggers"
        constraints = [
            models.UniqueConstraint(
                fields=["room_profile", "clue"],
                name="clue_trigger_unique_room_clue",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.clue.name} triggers in {self.room_profile}"


class ItemClueTrigger(SharedMemoryModel):
    """A clue granted passively on acquiring an item of a given kind — no search (#1160).

    The item-anchored counterpart to ``ClueTrigger`` (which fires on room entry): when a
    character acquires an item whose template carries an active trigger, is eligible (the
    predicate passes), and has not already held the clue, the clue is granted automatically
    ("acquiring an item your past-life soul is tied to"). Anchored on the item *kind*
    (``ItemTemplate``), so any instance of that kind fires it; some clue-bearing kinds will
    effectively spawn once, which is fine. Which kinds carry which clues under which predicate
    is staff-editable data (placeholder magnitudes deferred to a later author pass per #1143).
    """

    item_template = models.ForeignKey(
        "items.ItemTemplate",
        on_delete=models.CASCADE,
        related_name="clue_triggers",
    )
    clue = models.ForeignKey(
        Clue,
        on_delete=models.CASCADE,
        related_name="item_trigger_placements",
    )
    eligibility_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Predicate precondition for the passive grant (identity / resonance / org, via "
            "world.predicates). Empty {} = fires for anyone who acquires the item. Same shape "
            "as ClueTrigger.eligibility_rule."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this trigger currently fires on acquisition.",
    )

    class Meta:
        ordering = ["item_template", "clue"]
        verbose_name = "Item Clue Trigger"
        verbose_name_plural = "Item Clue Triggers"

    def __str__(self) -> str:
        return f"{self.clue.name} triggers on acquiring {self.item_template}"
