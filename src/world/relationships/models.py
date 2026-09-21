"""Models for ties between characters (#3957).

A tie is two directed sides. ``CharacterRelationship`` is one side: its labels
(``RelationshipLabel``), the depth it added (``scene_depth`` + ``invested_depth``),
the tier it has claimed, and the two play-moved gauges (``affection``, ``conflict``).
The pair's depth is the sum of both sides. Labels carry awareness and history and
are never deleted.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.contributors.models import CreditedContent
from world.magic.constants import SoulTetherRole
from world.relationships.constants import (
    BumpValence,
    DepthSource,
    LabelAwareness,
    TypeFamily,
    TypeValence,
)

# Cross-app FK string constants (SonarCloud python:S1192 duplicate-literal).
CHARACTER_SHEET_MODEL = "arxii.CharacterSheet"
SCENE_MODEL = "arxii.Scene"
COMPANION_MODEL = "arxii.Companion"
ROSTER_TENURE_MODEL = "arxii.RosterTenure"
GAME_WEEK_MODEL = "arxii.GameWeek"


class RelationshipCondition(SharedMemoryModel):
    """
    Conditions that can exist on a relationship.

    These represent specific states or feelings one character has toward another,
    such as "Attracted To", "Fears", "Trusts", etc. Conditions gate which
    situational modifiers (from distinctions, magic, etc.) apply during
    roll resolution.

    Examples:
    - "Attracted To" gates the Allure modifier from the Attractive distinction
    - "Fears" gates intimidation-related modifiers
    - "Trusts" gates persuasion-related modifiers
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Condition name (e.g., 'Attracted To', 'Fears', 'Trusts')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this condition represents",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display purposes (lower values appear first)",
    )

    # Which modifiers does this condition gate?
    gates_modifiers = models.ManyToManyField(
        "arxii.ModifierTarget",
        blank=True,
        related_name="gated_by_conditions",
        help_text="Modifier types that only apply when this condition exists",
    )

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name

    @cached_property
    def cached_gates_modifiers(self) -> list:
        """Modifier targets gated by this condition. Supports Prefetch(to_attr=)."""
        return list(self.gates_modifiers.all())


class RelationshipType(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """The catalogue of what one character may call another (#3957).

    Staff-authored, credited content (#2698). ``valence`` is what consent, journals and
    the surge engine read; ``family`` is how the picker groups the list; ``counterpart``
    is the type the OTHER side must hold for the label to be mutual (null = symmetric:
    Friend pairs with Friend; Mentor pairs with Student).
    """

    class NaturalKeyConfig:
        fields = ["name"]

    objects = NaturalKeyManager()

    name = models.CharField(max_length=100, unique=True, help_text="Type name, e.g. 'Rival'.")
    slug = models.SlugField(max_length=100, unique=True, help_text="URL-safe identifier.")
    description = models.TextField(
        blank=True, help_text="The one line shown in the picker. PLACEHOLDER copy."
    )
    family = models.CharField(max_length=20, choices=TypeFamily.choices, default=TypeFamily.COMPANY)
    valence = models.CharField(
        max_length=10, choices=TypeValence.choices, default=TypeValence.NEUTRAL
    )
    counterpart = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="counterpart_of",
        help_text="The type the other side must hold for this label to be mutual; null = itself.",
    )
    display_order = models.PositiveIntegerField(default=0)
    fuels_escalation_spikes = models.BooleanField(
        default=False,
        help_text=(
            "Whether a tie labelled with this type qualifies for combat escalation spikes "
            "when the other character falls or is fought as a hated foe (#872, #2013)."
        ),
    )

    class Meta:
        ordering = ["family", "display_order", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def counterpart_or_self(self) -> RelationshipType:
        return self.counterpart if self.counterpart_id is not None else self


class RelationshipTier(SharedMemoryModel):
    """One rung of the single tier ladder every tie shares (#3957)."""

    tier_number = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=100, help_text="PLACEHOLDER tier word.")
    depth_threshold = models.PositiveIntegerField(
        help_text="Pair depth a side needs before it may advance to this tier."
    )
    description = models.TextField(blank=True)
    combat_bonus = models.PositiveSmallIntegerField(
        default=0, help_text="The bond combat bonus a side at this tier grants."
    )

    class Meta:
        ordering = ["tier_number"]

    def __str__(self) -> str:
        return f"{self.name} (Tier {self.tier_number})"


class GrievanceOption(SharedMemoryModel):
    """An authored preset a wronged character may register (#1429); adds Conflict (#3957)."""

    label = models.CharField(max_length=60, unique=True, help_text="PLACEHOLDER flavor.")
    conflict_points = models.PositiveIntegerField(help_text="Conflict added on the victim's side.")
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "label"]

    def __str__(self) -> str:
        return f"{self.label} (+{self.conflict_points} conflict)"


class CharacterRelationship(SharedMemoryModel):
    """One character's side of a tie toward another character or a bonded companion (#3957).

    ``scene_depth`` and ``invested_depth`` are this side's added depth (audited by
    ``RelationshipDepthTransaction``); the pair's depth is ``pair_depth()``. ``tier`` is the
    tier this side has claimed by capstone and XP. ``affection`` and ``conflict`` are moved
    only by play (bumps, shifts, grievances, the NPC mirror). ``summary`` is the player's
    own paragraph. Labels hang off ``labels``.
    """

    source = models.ForeignKey(
        CHARACTER_SHEET_MODEL, on_delete=models.CASCADE, related_name="relationships_as_source"
    )
    target = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="relationships_as_target",
        help_text="Null when target_companion is set (#3575); exactly one is set.",
    )
    target_companion = models.ForeignKey(
        COMPANION_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="relationships_as_companion_target",
        help_text="The bonded companion this side is about (#3575); only its owner may hold it.",
    )
    is_active = models.BooleanField(default=True, help_text="A frozen side takes no credit.")
    conditions = models.ManyToManyField(
        RelationshipCondition, blank=True, related_name="character_relationships"
    )
    scene_depth = models.PositiveIntegerField(default=0, help_text="Depth from scenes together.")
    invested_depth = models.PositiveIntegerField(default=0, help_text="Depth from weekly AP.")
    tier = models.PositiveSmallIntegerField(default=0, help_text="The tier this side claimed.")
    affection = models.PositiveIntegerField(default=0, help_text="Moved by play, never set.")
    conflict = models.PositiveIntegerField(default=0, help_text="Moved by play, never set.")
    summary = models.TextField(blank=True, help_text="The player's own paragraph.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Soul-tether fields (Spec A §2.2); Spec B owns the mechanics.
    is_soul_tether = models.BooleanField(default=False)
    soul_tether_role = models.CharField(max_length=16, choices=SoulTetherRole.choices, blank=True)
    magical_flavor = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target"],
                condition=models.Q(target__isnull=False),
                name="unique_relationship_pair",
            ),
            models.UniqueConstraint(
                fields=["source", "target_companion"],
                condition=models.Q(target_companion__isnull=False),
                name="unique_relationship_companion_pair",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(target__isnull=False, target_companion__isnull=True)
                    | models.Q(target__isnull=True, target_companion__isnull=False)
                ),
                name="relationship_target_xor_companion",
            ),
            models.CheckConstraint(
                condition=~models.Q(source=models.F("target")),
                name="relationship_source_not_target",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source} -> {self.target_name}"

    @property
    def target_name(self) -> str:
        if self.target_companion_id is not None:
            return self.target_companion.name
        return self.target.character.db_key

    def clean(self) -> None:
        super().clean()
        if (self.target_id is not None) == (self.target_companion_id is not None):
            msg = "A relationship needs exactly one of a character target or a companion target."
            raise ValidationError(msg)
        if self.source_id is not None and self.source_id == self.target_id:
            msg = "A character cannot have a relationship with themselves."
            raise ValidationError(msg)

    @property
    def depth(self) -> int:
        """This side's added depth."""
        return self.scene_depth + self.invested_depth

    @cached_property
    def reverse(self) -> CharacterRelationship | None:
        """The other side's row, or None (always None toward a companion)."""
        if self.target_id is None:
            return None
        return CharacterRelationship.objects.filter(
            source_id=self.target_id, target_id=self.source_id
        ).first()

    def pair_depth(self) -> int:
        other = self.reverse
        return self.depth + (other.depth if other is not None else 0)

    def open_labels(self):
        return self.labels.filter(ended_at__isnull=True).select_related("type", "type__counterpart")

    def next_tier(self) -> RelationshipTier | None:
        return RelationshipTier.objects.filter(tier_number=self.tier + 1).first()

    @property
    def cached_conditions(self) -> list[RelationshipCondition]:
        try:
            return self._cached_conditions
        except AttributeError:
            return list(self.conditions.all())

    @cached_conditions.setter
    def cached_conditions(self, value: list[RelationshipCondition]) -> None:
        self._cached_conditions = value


class RelationshipLabel(SharedMemoryModel):
    """One side naming one type, at one awareness, with its history (#3957).

    Never deleted: a shift ends this row and starts another whose ``replaced`` points
    back here; an end sets ``ended_at`` and the label shows as former. Awareness only
    moves forward (``advance_awareness``). ``declared_by_tenure`` is read by consent only:
    a roster successor inherits the label but the RIVALS gate needs a label declared under
    a tenure that is still open.
    """

    relationship = models.ForeignKey(
        CharacterRelationship, on_delete=models.CASCADE, related_name="labels"
    )
    type = models.ForeignKey(RelationshipType, on_delete=models.PROTECT, related_name="labels")
    awareness = models.CharField(
        max_length=12, choices=LabelAwareness.choices, default=LabelAwareness.PRIVATE
    )
    declared_by_tenure = models.ForeignKey(
        ROSTER_TENURE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The tenure that declared it; consent reads whether it is still open.",
    )
    since = models.DateTimeField(default=timezone.now)
    clandestine_at = models.DateTimeField(null=True, blank=True)
    public_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    replaced = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replaced_by",
        help_text="The label this one was changed from.",
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["since"]
        constraints = [
            models.UniqueConstraint(
                fields=["relationship", "type"],
                condition=models.Q(ended_at__isnull=True),
                name="one_open_label_per_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type.name} on {self.relationship} ({self.awareness})"

    @property
    def is_former(self) -> bool:
        return self.ended_at is not None


class RelationshipAllocation(SharedMemoryModel):
    """This week's AP set against one side of a tie (#3957); mirrors ``TrainingAllocation``."""

    relationship = models.OneToOneField(
        CharacterRelationship, on_delete=models.CASCADE, related_name="allocation"
    )
    ap_amount = models.PositiveIntegerField(default=0)
    game_week = models.ForeignKey(
        GAME_WEEK_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.ap_amount} AP on {self.relationship}"


class RelationshipDepthTransaction(SharedMemoryModel):
    """Audit of one depth award to a side (#3957); the columns are the running sums."""

    relationship = models.ForeignKey(
        CharacterRelationship, on_delete=models.CASCADE, related_name="depth_transactions"
    )
    amount = models.PositiveIntegerField()
    source = models.CharField(max_length=12, choices=DepthSource.choices)
    scene = models.ForeignKey(
        SCENE_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    game_week = models.ForeignKey(
        GAME_WEEK_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"+{self.amount} {self.source} on {self.relationship}"


class RelationshipGrowthConfig(SharedMemoryModel):
    """Singleton tuning (pk=1) for how ties grow (#3957). All values PLACEHOLDER."""

    objects = ArxSharedMemoryManager()

    scene_base_gain = models.PositiveSmallIntegerField(
        default=10, help_text="Depth a side gains for the first scene together in a week."
    )
    depth_per_ap = models.PositiveSmallIntegerField(default=5)
    xp_per_tier = models.PositiveSmallIntegerField(
        default=10, help_text="Advance cost = this × the new tier."
    )
    thread_min_tier = models.PositiveSmallIntegerField(
        default=2, help_text="Claimed tier a weaver needs to weave a relationship thread."
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.AccountDB", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self) -> str:
        return f"RelationshipGrowthConfig(pk={self.pk})"


class RelationshipCapstone(SharedMemoryModel):
    """The receipt of one side advancing a tier (#3957), or a ritual formation event.

    ``journal_entry`` is the entry the player marked as the capstone; a ritual capstone
    (soul tether formation) has none and ``is_ritual_capstone`` says so.
    """

    relationship = models.ForeignKey(
        CharacterRelationship, on_delete=models.CASCADE, related_name="capstones"
    )
    journal_entry = models.OneToOneField(
        "arxii.JournalEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="capstone",
    )
    tier_claimed = models.PositiveSmallIntegerField(default=0)
    xp_spent = models.PositiveIntegerField(default=0)
    is_ritual_capstone = models.BooleanField(default=False)
    ritual = models.ForeignKey(
        "arxii.Ritual",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="capstone_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(journal_entry__isnull=False) | models.Q(is_ritual_capstone=True),
                name="capstone_has_entry_or_is_ritual",
            ),
        ]

    def __str__(self) -> str:
        return f"Capstone tier {self.tier_claimed} on {self.relationship}"

    @property
    def title(self) -> str:
        if self.journal_entry_id is not None:
            return self.journal_entry.title
        return "Soul Tether Formation"


class RelationshipBump(SharedMemoryModel):
    """An ambient ±1 relationship nudge anchored to the interaction that prompted it (#1699).

    Bumps are permanent, tiny, and ungated: rel plus/neg on telnet (backfill-
    anchored to the target's most recent unacknowledged pose) and valenced
    emoji reactions on the web both land here. The unique constraint per
    (relationship, interaction) IS the anti-spam mechanism: a pose can only be
    acknowledged once, so the per-scene budget (no more bumps than the target
    has posed) emerges without counters.
    """

    relationship = models.ForeignKey(
        CharacterRelationship,
        on_delete=models.CASCADE,
        related_name="bumps",
        help_text="The directed (source→target) relationship this bump nudges",
    )
    interaction = models.ForeignKey(
        "arxii.Interaction",
        on_delete=models.CASCADE,
        related_name="relationship_bumps",
        db_constraint=False,
        help_text="The pose/emit this bump acknowledges (anchor + dedup key)",
    )
    timestamp = models.DateTimeField(
        help_text="Denormalized from interaction for composite FK with partitioned table",
    )
    valence = models.SmallIntegerField(
        choices=BumpValence.choices,
        help_text="+1 warms (Regard system track), -1 cools (Friction system track)",
    )
    source_emoji = models.ForeignKey(
        "arxii.ReactionEmoji",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The catalog emoji that carried this bump (null = telnet rel plus/neg)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["relationship", "interaction"],
                name="unique_bump_per_interaction",
            ),
        ]

    def __str__(self) -> str:
        sign = "+" if self.valence > 0 else "-"
        return f"Bump {sign}1 on {self.relationship} @ interaction {self.interaction_id}"


class AffectionShift(SharedMemoryModel):
    """A social action's automatic affection shift on its target's regard (#1697).

    The generic, valence-signed success consequence (SHIFT_AFFECTION): a
    successful Flirt (+5) or Seduce (+50) — and gated offensive actions
    with negative amounts — moves the TARGET's relationship toward the actor
    on the Regard/Friction system tracks. Two provenance modes (#2540):
    effect-keyed rows keep the per-(relationship, scene, effect)
    diminishing-returns rule — only the first success of a given effect per
    scene per pair shifts; repeats no-op (conditions still refresh) — while
    boon-keyed rows dedup on the Boon itself, so serial granted boons stack
    even within one scene (each ask wears out more welcome).
    """

    relationship = models.ForeignKey(
        CharacterRelationship,
        on_delete=models.CASCADE,
        related_name="affection_shifts",
        help_text="The directed (target→actor) relationship this shift moved",
    )
    scene = models.ForeignKey(
        SCENE_MODEL,
        on_delete=models.CASCADE,
        related_name="affection_shifts",
        help_text="The scene the shifting action resolved in (dedup key)",
    )
    effect = models.ForeignKey(
        "arxii.ConsequenceEffect",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="affection_shifts",
        help_text="The SHIFT_AFFECTION effect row that fired (dedup key + provenance)",
    )
    boon = models.OneToOneField(
        "arxii.Boon",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="affection_shift",
        help_text="The granted Boon this shift charges (#2540) — per-Boon dedup, stacking. "
        "CASCADE (not SET_NULL): affection_shift_has_provenance requires effect-or-boon "
        "non-null, so a boon-keyed row's provenance dies with the boon.",
    )
    amount = models.IntegerField(
        help_text="Signed points applied: positive → Regard, negative → Friction",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["relationship", "scene", "effect"],
                condition=models.Q(boon__isnull=True),
                name="unique_affection_shift_per_scene",
            ),
            models.CheckConstraint(
                condition=models.Q(effect__isnull=False) | models.Q(boon__isnull=False),
                name="affection_shift_has_provenance",
            ),
        ]

    def __str__(self) -> str:
        return f"AffectionShift {self.amount:+d} on {self.relationship} (scene {self.scene_id})"


class TemporaryRelationshipCondition(SharedMemoryModel):
    """A time-limited :class:`RelationshipCondition` on a directed relationship (#1697).

    Permanent conditions ("Attracted To") live on ``CharacterRelationship.conditions`` (the M2M).
    Temporary ones ("Very Attracted" from a flirt) live here with an ``expires_at``, so they drop
    off while the permanent condition persists. The allure engine
    (``relationship_gated_contributions``) unions the active (non-expired) rows here with the
    permanent M2M — counting allure once per gating condition, so an active Very Attracted is the
    second (doubling) allure application. Pruned by a game_clock cron.
    """

    relationship = models.ForeignKey(
        CharacterRelationship,
        on_delete=models.CASCADE,
        related_name="temporary_conditions",
    )
    condition = models.ForeignKey(
        RelationshipCondition,
        on_delete=models.CASCADE,
        related_name="temporary_applications",
    )
    expires_at = models.DateTimeField(help_text="When this temporary condition lapses.")
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["relationship", "condition"], name="uniq_temp_relationship_condition"
            )
        ]
        # Prune query is (relationship, expires_at); the unique constraint already indexes
        # (relationship, condition), so no duplicate index there.
        indexes = [models.Index(fields=["relationship", "expires_at"])]

    def __str__(self) -> str:
        return f"{self.condition.name} on {self.relationship} (until {self.expires_at:%Y-%m-%d})"


class BondCombatConfig(SharedMemoryModel):
    """Singleton tuning surface (pk=1) for the bond combat bonus (#2021, #3957)."""

    objects = ArxSharedMemoryManager()

    min_tier = models.PositiveSmallIntegerField(
        default=1, help_text="Claimed tier below which a side grants no combat bonus."
    )
    soul_tether_multiplier = models.PositiveSmallIntegerField(default=2)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bond_combat_config_updates",
    )

    def __str__(self) -> str:
        return f"BondCombatConfig(pk={self.pk})"
