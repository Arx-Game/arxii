"""Standoff models: creature motives, regard rules, approaches, terms and live groups.

A standoff is the stretch before a fight (``CombatEncounter.round_number == 0``) in
which each group of creatures can be read and talked down. "In a standoff" is derived
from an OPEN ``StandoffGroup`` existing; there is no flag on the encounter.
Drives and cause are read through ``CombatOpponent.creature_template``.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.predicates.validation import validate_predicate_tree
from world.standoffs.constants import (
    DriveStrength,
    RevealKind,
    StandoffGroupState,
    TermsEffect,
)


class CreatureDrive(SharedMemoryModel):
    """One thing a kind of creature wants, and how badly (a Property it cares about)."""

    creature_template = models.ForeignKey(
        "arxii.CreatureTemplate",
        on_delete=models.CASCADE,
        related_name="drives",
        help_text="The creature kind that has this drive.",
    )
    property = models.ForeignKey(
        "arxii.Property",
        on_delete=models.PROTECT,
        related_name="creature_drives",
        help_text="What the creature wants (a Property such as hunger or greed).",
    )
    strength = models.PositiveSmallIntegerField(
        choices=DriveStrength.choices,
        default=DriveStrength.MINOR,
        help_text="How hard this drive pulls on the creature.",
    )

    class Meta:
        ordering = ["creature_template", "-strength", "property"]
        constraints = [
            models.UniqueConstraint(
                fields=["creature_template", "property"],
                name="unique_drive_per_template_property",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.creature_template} drive: {self.property} ({self.get_strength_display()})"


class RegardRule(SharedMemoryModel):
    """How a creature kind regards particular characters, and what that does to a standoff.

    ``rule`` is a predicate tree over the acting character's own state (ratified
    exception to the no-JSON rule, ADR-0007). Deed knowledge is the typed
    ``deed_archetype`` field, since predicate leaves cannot read other people's state.
    """

    creature_template = models.ForeignKey(
        "arxii.CreatureTemplate",
        on_delete=models.CASCADE,
        related_name="regard_rules",
        help_text="The creature kind this rule belongs to.",
    )
    # SANCTIONED DYNAMIC JSON: a predicate rule tree (AND/OR/NOT over the acting
    # character's own state), validated by ``validate_predicate_tree`` in clean().
    # Covered by ADR-0007's ratified predicate exception, the same one the missions
    # ``visibility_rule`` uses. No other JSONField is permitted in standoffs.
    rule = models.JSONField(
        default=dict,
        blank=True,
        help_text="Predicate tree over the character's own state; empty matches everyone.",
    )
    deed_archetype = models.ForeignKey(
        "arxii.PhilosophicalArchetype",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Matches a character whose common-knowledge deeds show this archetype.",
    )
    difficulty_shift_bands = models.SmallIntegerField(
        default=0,
        help_text="Bands added to (positive) or taken from (negative) the standoff difficulty.",
    )
    drive = models.ForeignKey(
        "arxii.Property",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="A drive this rule strengthens or weakens, if any.",
    )
    drive_shift = models.SmallIntegerField(
        default=0,
        help_text="Steps added to the named drive's strength when this rule matches.",
    )
    suppresses_cause = models.BooleanField(
        default=False,
        help_text="When true, a match stops the creature's cause from firing.",
    )
    spark_text = models.TextField(
        blank=True,
        help_text="Player-visible hint at the character's own reaction (author in admin).",
    )
    revealed_text = models.TextField(
        blank=True,
        help_text="Player-visible text once a read reveals this rule (author in admin).",
    )

    class Meta:
        ordering = ["creature_template", "pk"]

    def __str__(self) -> str:
        return f"{self.creature_template} regard rule #{self.pk}"

    def clean(self) -> None:
        super().clean()
        errors = validate_predicate_tree(self.rule)
        if errors:
            raise ValidationError({"rule": errors})
        if (
            self.drive_id is not None
            and self.creature_template_id is not None
            and not self.creature_template.drives.filter(property_id=self.drive_id).exists()
        ):
            raise ValidationError({"drive": "The creature kind has no drive on that property."})


class StandoffApproach(NaturalKeyMixin, SharedMemoryModel):
    """A way to press a group in a standoff (intimidate, charm, bluff...)."""

    name = models.CharField(max_length=100, unique=True, help_text="Name shown to players.")
    check_type = models.ForeignKey(
        "arxii.CheckType",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The check rolled when a character uses this approach.",
    )
    capability = models.ForeignKey(
        "arxii.CapabilityType",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The capability this approach draws on.",
    )
    sway_target = models.ForeignKey(
        "arxii.ModifierTarget",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="The modifier target that adds sway to this approach, if any.",
    )
    damages_morale = models.BooleanField(
        default=False,
        help_text="When true, a success also wears down the group's morale.",
    )
    archetypes = models.ManyToManyField(
        "arxii.PhilosophicalArchetype",
        blank=True,
        related_name="+",
        help_text="Archetypes this approach suits; empty means any.",
    )
    display_order = models.PositiveIntegerField(default=0, help_text="Lower values show first.")

    objects = NaturalKeyManager()

    class Meta:
        ordering = ["display_order", "name"]

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class StandoffTerms(NaturalKeyMixin, SharedMemoryModel):
    """A set of terms offered to a group (let us pass, clear off, turn, pay us)."""

    name = models.CharField(max_length=100, unique=True, help_text="Name shown to players.")
    effect = models.CharField(
        max_length=20,
        choices=TermsEffect.choices,
        help_text="What happens to the group when the terms are accepted.",
    )
    description = models.TextField(
        blank=True,
        help_text="Outcome shown to players before they commit to these terms (author in admin).",
    )
    required_drive = models.ForeignKey(
        "arxii.Property",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="A drive the group must have for these terms to be offered, if any.",
    )
    difficulty_shift_bands = models.SmallIntegerField(
        default=0,
        help_text="Bands added to (positive) or taken from (negative) the terms difficulty.",
    )
    archetypes = models.ManyToManyField(
        "arxii.PhilosophicalArchetype",
        blank=True,
        related_name="+",
        help_text="Archetypes these terms suit; empty means any.",
    )
    display_order = models.PositiveIntegerField(default=0, help_text="Lower values show first.")

    objects = NaturalKeyManager()

    class Meta:
        ordering = ["display_order", "name"]

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class StandoffConfig(SharedMemoryModel):
    """Singleton (pk=1): the tuning knobs for standoffs."""

    read_check_type = models.ForeignKey(
        "arxii.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The check rolled to read a group.",
    )
    terms_check_type = models.ForeignKey(
        "arxii.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The check rolled to press terms on a group.",
    )
    pass_condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Condition applied to a group that lets the party pass.",
    )
    turn_condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Condition applied to a group that turns to the party's side.",
    )
    botch_force_bands = models.PositiveSmallIntegerField(
        default=1, help_text="Bands of group force a botched press adds."
    )
    over_level_percent_per_tier = models.PositiveSmallIntegerField(
        default=25,
        help_text=(
            "Percent of party force added for each tier of levels the party average stands "
            "above the mission's level band, or taken off for each tier below it."
        ),
    )
    falter_force_percent = models.PositiveSmallIntegerField(
        default=70,
        help_text="Percent of its force a faltering opponent still counts for in a standoff.",
    )
    break_force_percent = models.PositiveSmallIntegerField(
        default=40,
        help_text="Percent of its force a broken opponent still counts for in a standoff.",
    )
    band_force_percent = models.PositiveSmallIntegerField(
        default=10, help_text="Percent of party force one band of emboldening takes away."
    )

    objects = ArxSharedMemoryManager()

    class Meta:
        ordering = ["pk"]

    @classmethod
    def load(cls) -> StandoffConfig:
        """Fetch (or lazily create) the singleton row."""
        obj = cls.objects.cached_singleton()
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self) -> str:
        return "Standoff settings"


class StandoffGroup(SharedMemoryModel):
    """One creature kind's opponents in an encounter, treated as a single side of a standoff."""

    encounter = models.ForeignKey(
        "arxii.CombatEncounter",
        on_delete=models.CASCADE,
        related_name="standoff_groups",
        help_text="The encounter this standoff belongs to.",
    )
    creature_template = models.ForeignKey(
        "arxii.CreatureTemplate",
        on_delete=models.CASCADE,
        related_name="standoff_groups",
        help_text="The creature kind that makes up the group.",
    )
    state = models.CharField(
        max_length=20,
        choices=StandoffGroupState.choices,
        default=StandoffGroupState.OPEN,
        help_text="Where the group stands.",
    )
    terms_ease = models.PositiveSmallIntegerField(
        default=0, help_text="How many successful presses have softened the group."
    )
    emboldened_bands = models.PositiveSmallIntegerField(
        default=0, help_text="Bands of force the group has gained from botched presses."
    )
    settled_outcome = models.ForeignKey(
        "arxii.CheckOutcome",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The outcome that settled the group, once it is settled.",
    )

    class Meta:
        ordering = ["encounter", "creature_template"]
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "creature_template"],
                name="unique_standoff_group_per_encounter_template",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.creature_template} in encounter {self.encounter_id} ({self.state})"


class StandoffReveal(SharedMemoryModel):
    """One thing a read has uncovered about a group: its cause, a drive, or a regard rule."""

    group = models.ForeignKey(
        StandoffGroup,
        on_delete=models.CASCADE,
        related_name="reveals",
        help_text="The group the reveal is about.",
    )
    kind = models.CharField(
        max_length=20, choices=RevealKind.choices, help_text="What sort of thing was revealed."
    )
    drive = models.ForeignKey(
        CreatureDrive,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="The drive revealed (DRIVE reveals only).",
    )
    regard_rule = models.ForeignKey(
        RegardRule,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="The regard rule revealed (REGARD reveals only).",
    )

    class Meta:
        ordering = ["group", "kind", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind=RevealKind.CAUSE, drive__isnull=True, regard_rule__isnull=True)
                    | models.Q(kind=RevealKind.DRIVE, drive__isnull=False, regard_rule__isnull=True)
                    | models.Q(
                        kind=RevealKind.REGARD, drive__isnull=True, regard_rule__isnull=False
                    )
                ),
                name="standoff_reveal_fk_matches_kind",
            ),
            models.UniqueConstraint(
                fields=["group", "kind", "drive", "regard_rule"],
                name="unique_standoff_reveal",
                nulls_distinct=False,
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} reveal for {self.group}"


class StandoffSparkShare(SharedMemoryModel):
    """A character's spark text for a regard rule, shared with the rest of the party."""

    group = models.ForeignKey(
        StandoffGroup,
        on_delete=models.CASCADE,
        related_name="spark_shares",
        help_text="The group the spark is about.",
    )
    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The character whose spark was shared.",
    )
    regard_rule = models.ForeignKey(
        RegardRule,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The regard rule the spark came from.",
    )

    class Meta:
        ordering = ["group", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "character_sheet", "regard_rule"],
                name="unique_standoff_spark_share",
            ),
        ]

    def __str__(self) -> str:
        return f"Spark share for {self.group}"
