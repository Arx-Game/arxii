"""Standoff models: creature motives, faction rules, approaches, terms and live groups.

A standoff is the stretch before a fight (``CombatEncounter.round_number == 0``) in
which each group of creatures can be read and talked down. "In a standoff" is derived
from an OPEN ``StandoffGroup`` existing; there is no flag on the encounter.
Drives, cause and affiliation are stamped on each ``CombatOpponent`` at spawn (#4361); a
live encounter reads the snapshot, never the template (``services.profile``).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.combat.constants import CauseKind
from world.predicates.validation import validate_predicate_tree
from world.standoffs.constants import (
    CauseEffect,
    DriveStrength,
    MoraleDirection,
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


class FactionRule(SharedMemoryModel):
    """How a group stands toward particular characters, and what that does to a standoff.

    Owned by exactly one of a creature template, an organization or a society (#4361).
    An opponent carries its template's rules plus those of its affiliation organization,
    that organization's ``parent_org`` chain and each of their societies; where two rules
    shift the same thing, the most specific owner wins (``services.profile``).

    ``rule`` is a predicate tree over the acting character's own state (ratified
    exception to the no-JSON rule, ADR-0007). Deed knowledge is the typed
    ``deed_archetype`` field, since predicate leaves cannot read other people's state.
    """

    creature_template = models.ForeignKey(
        "arxii.CreatureTemplate",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="faction_rules",
        help_text="The creature kind this rule belongs to (set this, an organization or a "
        "society).",
    )
    organization = models.ForeignKey(
        "arxii.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="faction_rules",
        help_text="The organization whose people hold this rule; inherited by every creature "
        "affiliated with it or with an organization below it.",
    )
    society = models.ForeignKey(
        "arxii.Society",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="faction_rules",
        help_text="The society whose people hold this rule; inherited by every creature "
        "affiliated with one of its organizations.",
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
    cause_effect = models.CharField(
        max_length=10,
        choices=CauseEffect.choices,
        default=CauseEffect.NONE,
        help_text=(
            "None, Suppress (they will not start it against this character) or Provoke "
            "(they will, whatever the force)."
        ),
    )
    angle_text = models.TextField(
        blank=True,
        help_text="Player-visible hint at the character's own reaction (author in admin).",
    )
    revealed_text = models.TextField(
        blank=True,
        help_text="Player-visible text once a read reveals this rule (author in admin).",
    )

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        creature_template__isnull=False,
                        organization__isnull=True,
                        society__isnull=True,
                    )
                    | models.Q(
                        creature_template__isnull=True,
                        organization__isnull=False,
                        society__isnull=True,
                    )
                    | models.Q(
                        creature_template__isnull=True,
                        organization__isnull=True,
                        society__isnull=False,
                    )
                ),
                name="faction_rule_one_owner",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.owner} faction rule #{self.pk}"

    @property
    def owner(self) -> object:
        """The creature template, organization or society this rule belongs to."""
        return self.creature_template or self.organization or self.society

    def clean(self) -> None:
        super().clean()
        errors = validate_predicate_tree(self.rule)
        if errors:
            raise ValidationError({"rule": errors})
        owners = [self.creature_template_id, self.organization_id, self.society_id]
        if sum(owner is not None for owner in owners) != 1:
            msg = "A faction rule belongs to exactly one creature, organization or society."
            raise ValidationError(msg)
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
    is_verbal = models.BooleanField(
        default=False,
        help_text=("Refused against a group that shares no language with the actor."),
    )
    casts_technique = models.BooleanField(
        default=False,
        help_text=(
            "The player picks one of their techniques; its cast is the check, and nobody is harmed."
        ),
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
    critical_effect = models.CharField(
        max_length=20,
        choices=TermsEffect.choices,
        blank=True,
        help_text=(
            "The effect applied INSTEAD of the usual one on a critical success; blank means "
            "a critical does the same as any success. Any toll comes from the mission's own "
            "reward lines on the critical tier."
        ),
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

    def clean(self) -> None:
        super().clean()
        if self.critical_effect and self.critical_effect == self.effect:
            raise ValidationError(
                {"critical_effect": "A critical upgrade must differ from the usual effect."}
            )


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

    terms_ease_faltering = models.PositiveSmallIntegerField(
        default=1, help_text="Terms steps eased when the group is faltering."
    )
    terms_ease_broken = models.PositiveSmallIntegerField(
        default=2, help_text="Terms steps eased when the group is broken."
    )
    regard_per_band = models.PositiveSmallIntegerField(
        default=100,
        validators=[MinValueValidator(1)],
        help_text=(
            "NPC regard points per band: a named NPC's regard for the actor eases (positive) "
            "or hardens (negative) a press or terms by one band for each full step (#4373)."
        ),
    )
    regard_max_bands = models.PositiveSmallIntegerField(
        default=3,
        help_text="The most bands a named NPC's regard can ease or harden a press or terms.",
    )
    hunger_margin_step = models.PositiveSmallIntegerField(
        default=10,
        help_text=("Percent added to a Hunger group's margin for each action nobody feeds them."),
    )
    territory_patience = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1)],
        help_text=(
            "Actions a Territory group allows before it fires. They warn one action earlier."
        ),
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


class StandoffCauseGloss(NaturalKeyMixin, SharedMemoryModel):
    """The one-line player-facing gloss shown under a revealed cause (author in admin).

    One row per ``CauseKind``. A cause with no row shows no gloss; the Required content
    dashboard lists the kinds still missing one.
    """

    cause = models.CharField(
        max_length=20,
        choices=CauseKind.choices,
        unique=True,
        help_text="The cause this gloss explains.",
    )
    text = models.CharField(
        max_length=200,
        help_text="Shown to the party under the cause once a read reveals it (author in admin).",
    )

    objects = NaturalKeyManager()

    class Meta:
        ordering = ["cause"]

    class NaturalKeyConfig:
        fields = ["cause"]

    def __str__(self) -> str:
        return f"{self.get_cause_display()} gloss"


class StandoffGroup(SharedMemoryModel):
    """One side of a standoff: a creature kind's opponents, or one named NPC (#4373).

    A template group is every active opponent of ``creature_template`` with no persona. A
    persona group is the one opponent standing as ``persona``; its ``creature_template`` is
    the template it was spawned from, if any.
    """

    encounter = models.ForeignKey(
        "arxii.CombatEncounter",
        on_delete=models.CASCADE,
        related_name="standoff_groups",
        help_text="The encounter this standoff belongs to.",
    )
    creature_template = models.ForeignKey(
        "arxii.CreatureTemplate",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="standoff_groups",
        help_text="The creature kind that makes up the group (a named NPC's template, if any).",
    )
    persona = models.ForeignKey(
        "arxii.Persona",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="The named NPC this group is, when it is one person (#4373).",
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
    proposal_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Why the cause last fired, shown on the GM's proposal (system text).",
    )
    override_party_force = models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "Party force when a GM overrode the cause; the cause is not tested again until "
            "force moves off this value or a botch lands. Null when no override stands."
        ),
    )
    override_group_force = models.FloatField(
        null=True,
        blank=True,
        help_text="Group force when a GM overrode the cause (see override_party_force).",
    )
    actions_elapsed = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Party actions taken in the standoff while this group stood in it: widens a Hunger "
            "margin and runs down a Territory group's patience."
        ),
    )

    class Meta:
        ordering = ["encounter", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "creature_template", "persona"],
                name="unique_standoff_group_per_encounter_template_persona",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(creature_template__isnull=False) | models.Q(persona__isnull=False)
                ),
                name="standoff_group_template_or_persona",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} in encounter {self.encounter_id} ({self.state})"

    @property
    def name(self) -> str:
        """What players call the group: the named NPC, or the creature kind."""
        if self.persona_id is not None:
            return self.persona.name
        return self.creature_template.name

    @property
    def referent(self) -> str:
        """The group inside a room line: "Maud Carrow", or "the Sellswords"."""
        return self.name if self.persona_id is not None else f"the {self.name}"


class StandoffReveal(SharedMemoryModel):
    """One thing a read has uncovered about a group: its cause, a drive, or a faction rule."""

    group = models.ForeignKey(
        StandoffGroup,
        on_delete=models.CASCADE,
        related_name="reveals",
        help_text="The group the reveal is about.",
    )
    kind = models.CharField(
        max_length=20, choices=RevealKind.choices, help_text="What sort of thing was revealed."
    )
    faction_rule = models.ForeignKey(
        FactionRule,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="The faction rule revealed ((FACTION_RULE reveals only)).",
    )
    drive = models.ForeignKey(
        "arxii.Property",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The drive revealed, by its property (DRIVE reveals only). A group's drives are "
            "stamped on its members at spawn, so a placement may add one its template lacks."
        ),
    )

    class Meta:
        ordering = ["group", "kind", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind=RevealKind.CAUSE, drive__isnull=True, faction_rule__isnull=True)
                    | models.Q(
                        kind=RevealKind.DRIVE, drive__isnull=False, faction_rule__isnull=True
                    )
                    | models.Q(
                        kind=RevealKind.FACTION_RULE, drive__isnull=True, faction_rule__isnull=False
                    )
                ),
                name="standoff_reveal_fk_matches_kind",
            ),
            models.UniqueConstraint(
                fields=["group", "kind", "drive", "faction_rule"],
                name="unique_standoff_reveal",
                nulls_distinct=False,
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} reveal for {self.group}"


class StandoffAngleShare(SharedMemoryModel):
    """A character's angle text for a faction rule, shared with the rest of the party."""

    group = models.ForeignKey(
        StandoffGroup,
        on_delete=models.CASCADE,
        related_name="angle_shares",
        help_text="The group the angle is about.",
    )
    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The character whose angle was shared.",
    )
    faction_rule = models.ForeignKey(
        FactionRule,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The faction rule the angle came from.",
    )

    class Meta:
        ordering = ["group", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "character_sheet", "faction_rule"],
                name="unique_standoff_angle_share",
            ),
        ]

    def __str__(self) -> str:
        return f"Angle share for {self.group}"


class StandoffReactionLine(SharedMemoryModel):
    """Authored flavour for how a press or terms roll lands, banded by success level.

    Staff author these (the owner's rule: someone awesome must feel it). The highest
    ``min_success_level`` that is <= the roll's level wins; a line tied to one creature
    kind beats a generic line at the same floor. ``<actor>`` is replaced by the name the
    actor presents under and ``<group>`` by the creature kind's name. Unlike
    ``NPCReactionLine`` (NPC role/functionary, banded on a character metric) this belongs
    to a standoff approach or terms row and bands on the roll itself.
    """

    approach = models.ForeignKey(
        StandoffApproach,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reaction_lines",
        help_text="The approach this line reacts to (set this or terms, not both).",
    )
    terms = models.ForeignKey(
        StandoffTerms,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reaction_lines",
        help_text="The terms this line reacts to (set this or approach, not both).",
    )
    creature_template = models.ForeignKey(
        "arxii.CreatureTemplate",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="When set, the line applies only to this creature kind and beats a generic "
        "line at the same floor.",
    )
    min_success_level = models.SmallIntegerField(
        help_text="Line applies from this success level up (-2 critical failure to 2 critical "
        "success); the highest floor at or below the roll wins.",
    )
    text = models.TextField(
        help_text="The line shown to the room (author in admin). <actor> is the presented "
        "name, <group> the creature kind.",
    )

    class Meta:
        ordering = ["approach", "terms", "-min_success_level"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(approach__isnull=False, terms__isnull=True)
                    | models.Q(approach__isnull=True, terms__isnull=False)
                ),
                name="standoff_reaction_line_one_parent",
            ),
        ]

    def __str__(self) -> str:
        return f"Reaction line #{self.pk} (>= {self.min_success_level})"


class StandoffMoraleRuling(SharedMemoryModel):
    """A GM moved a group's morale one state, and why (#4354). The GM's own record."""

    group = models.ForeignKey(
        StandoffGroup,
        on_delete=models.CASCADE,
        related_name="morale_rulings",
        help_text="The group whose morale the GM moved.",
    )
    ruled_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The GM account that made the ruling.",
    )
    direction = models.CharField(
        max_length=10, choices=MoraleDirection.choices, help_text="Shake or steady."
    )
    reason = models.TextField(help_text="The GM's stated reason (required).")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["group", "-created_at"]

    def __str__(self) -> str:
        return f"{self.get_direction_display()} on {self.group}"


def _one_line_constraint(name: str) -> models.CheckConstraint:
    """Exactly one of ``beat_line`` and ``mission_line`` is set on a placement edit (#4361)."""
    return models.CheckConstraint(
        condition=(
            models.Q(beat_line__isnull=False, mission_line__isnull=True)
            | models.Q(beat_line__isnull=True, mission_line__isnull=False)
        ),
        name=name,
    )


class OpponentLineDrive(SharedMemoryModel):
    """One placement's change to a drive: a new strength, an added drive, or a removal.

    A blank ``strength`` removes the template's drive on that property for this placement
    only. Picked from the property catalog (ADR-0110: GMs adapt authored rows).
    """

    # Declared before the ``property`` field, which shadows the builtin in this class body.
    @property
    def line(self) -> object:
        """The placement this edit belongs to (exactly one of the two lines is set)."""
        return self.beat_line or self.mission_line

    beat_line = models.ForeignKey(
        "arxii.BeatOpponentLine",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="drive_edits",
        help_text="The beat opponent line this edit belongs to (set this or mission_line).",
    )
    mission_line = models.ForeignKey(
        "arxii.MissionOptionOpponentLine",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="drive_edits",
        help_text="The mission option opponent line this edit belongs to (or beat_line).",
    )
    property = models.ForeignKey(
        "arxii.Property",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The drive this placement changes or adds.",
    )
    strength = models.PositiveSmallIntegerField(
        choices=DriveStrength.choices,
        null=True,
        blank=True,
        help_text="The strength here. Blank removes the template's drive for this placement.",
    )

    class Meta:
        ordering = ["pk"]
        constraints = [
            _one_line_constraint("opponent_line_drive_one_line"),
            models.UniqueConstraint(
                fields=["beat_line", "property"],
                condition=models.Q(beat_line__isnull=False),
                name="unique_beat_line_drive_property",
            ),
            models.UniqueConstraint(
                fields=["mission_line", "property"],
                condition=models.Q(mission_line__isnull=False),
                name="unique_mission_line_drive_property",
            ),
        ]

    def __str__(self) -> str:
        strength = self.get_strength_display() if self.strength else "removed"
        return f"{self.property} ({strength}) on {self.line}"


class OpponentLineFactionRuleSuppression(SharedMemoryModel):
    """One placement switches off one inherited faction rule (#4361)."""

    beat_line = models.ForeignKey(
        "arxii.BeatOpponentLine",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="faction_rule_suppressions",
        help_text="The beat opponent line this belongs to (set this or mission_line).",
    )
    mission_line = models.ForeignKey(
        "arxii.MissionOptionOpponentLine",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="faction_rule_suppressions",
        help_text="The mission option opponent line this belongs to (or beat_line).",
    )
    faction_rule = models.ForeignKey(
        FactionRule,
        on_delete=models.CASCADE,
        related_name="suppressions",
        help_text="The inherited faction rule switched off for this placement.",
    )

    class Meta:
        ordering = ["pk"]
        constraints = [
            _one_line_constraint("opponent_line_suppression_one_line"),
            models.UniqueConstraint(
                fields=["beat_line", "faction_rule"],
                condition=models.Q(beat_line__isnull=False),
                name="unique_beat_line_suppression",
            ),
            models.UniqueConstraint(
                fields=["mission_line", "faction_rule"],
                condition=models.Q(mission_line__isnull=False),
                name="unique_mission_line_suppression",
            ),
        ]

    @property
    def line(self) -> object:
        """The placement this suppression belongs to (exactly one of the two lines is set)."""
        return self.beat_line or self.mission_line

    def __str__(self) -> str:
        return f"{self.faction_rule} off on {self.line}"
