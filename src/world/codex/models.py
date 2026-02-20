"""
Codex system models.

Lore storage and character knowledge tracking. Characters can learn entries
from starting choices (Beginnings, Path, Distinctions) or through teaching.
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.action_points.models import ActionPointPool
from world.codex.constants import CodexKnowledgeStatus
from world.consent.models import VisibilityMixin
from world.roster.models import RosterEntry, RosterTenure


class CodexCategory(NaturalKeyMixin, SharedMemoryModel):
    """
    Top-level category for lore.

    Examples: "Arx Lore", "Umbral Lore", "Magic Traditions"
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name of this category.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what lore this category contains.",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display in lists.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Codex Category"
        verbose_name_plural = "Codex Categories"

    def __str__(self) -> str:
        return self.name


class CodexSubject(NaturalKeyMixin, SharedMemoryModel):
    """
    A subject within a category. Nestable via parent FK.

    Examples:
    - "The Shroud" (parent=None, top-level subject)
    - "The Flickering" (parent="The Shroud", nested subject)
    """

    category = models.ForeignKey(
        CodexCategory,
        on_delete=models.CASCADE,
        related_name="subjects",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        help_text="Parent subject for nesting. Leave blank for top-level.",
    )
    name = models.CharField(
        max_length=100,
        help_text="Name of this subject.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this subject.",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display within parent/category.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["category", "parent", "name"]
        dependencies = ["codex.CodexCategory"]

    class Meta:
        ordering = ["display_order", "name"]
        unique_together = ["category", "parent", "name"]
        verbose_name = "Codex Subject"
        verbose_name_plural = "Codex Subjects"

    def __str__(self) -> str:
        if self.parent:
            return f"{self.parent} > {self.name}"
        return f"{self.category}: {self.name}"

    @property
    def breadcrumb_path(self) -> list[dict]:
        """Return path from category to this subject with IDs for navigation.

        Note: Named breadcrumb_path to avoid collision with SharedMemoryModel's
        path attribute set by the metaclass.

        Each element is {"type": "category"|"subject", "id": int, "name": str}.
        Uses iterative traversal. Views should use select_related with bounded
        depth to avoid N+1 queries when accessing parent chain.
        """
        parts: list[dict] = [{"type": "subject", "id": self.pk, "name": self.name}]
        current = self.parent
        while current:
            parts.insert(0, {"type": "subject", "id": current.pk, "name": current.name})
            current = current.parent
        parts.insert(0, {"type": "category", "id": self.category_id, "name": self.category.name})
        return parts


class CodexEntry(NaturalKeyMixin, SharedMemoryModel):
    """
    An individual piece of lore that can be known/taught/learned.
    """

    subject = models.ForeignKey(
        CodexSubject,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    name = models.CharField(
        max_length=200,
        help_text="Title of this entry.",
    )
    summary = models.CharField(
        max_length=300,
        blank=True,
        help_text="Short summary for tooltips/modals (1-2 sentences).",
    )
    lore_content = models.TextField(
        blank=True,
        null=True,
        help_text="In-character world flavor/lore content.",
    )
    mechanics_content = models.TextField(
        blank=True,
        null=True,
        help_text="Out-of-character mechanical explanation.",
    )
    prerequisites = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="unlocks",
        help_text="Entries required before this can be learned.",
    )
    share_cost = models.PositiveIntegerField(
        default=5,
        help_text="AP cost for teacher to offer this entry.",
    )
    learn_cost = models.PositiveIntegerField(
        default=5,
        help_text="AP cost for learner to accept an offer.",
    )
    learn_difficulty = models.PositiveIntegerField(
        default=10,
        help_text="Base difficulty for learning progress checks.",
    )
    learn_threshold = models.PositiveIntegerField(
        default=10,
        help_text="Total progress needed to complete learning.",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display within subject.",
    )
    is_public = models.BooleanField(
        default=False,
        help_text="If True, visible to everyone including logged-out visitors. "
        "If False, only visible to characters who have learned it.",
    )
    modifier_type = models.OneToOneField(
        "mechanics.ModifierType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="codex_entry",
        help_text="Link to a modifier type this entry documents (for resonances, stats, etc.).",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["subject", "name"]
        dependencies = ["codex.CodexSubject"]

    class Meta:
        ordering = ["display_order", "name"]
        unique_together = ["subject", "name"]
        verbose_name = "Codex Entry"
        verbose_name_plural = "Codex Entries"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """Validate that at least one content field is provided."""
        super().clean()
        if not self.lore_content and not self.mechanics_content:
            msg = "At least one of lore_content or mechanics_content must be provided."
            raise ValidationError(msg)


class CharacterCodexKnowledge(models.Model):
    """
    Tracks what a character knows or is learning.

    Uses RosterEntry because knowledge belongs to the character itself -
    if a character changes hands, the new player inherits what the
    character knows.

    Learning progress tracks accumulated progress toward threshold,
    not ticks remaining (allows for variable/chance-based advancement).
    """

    # Alias for backward compatibility — canonical definition is in constants.py
    Status = CodexKnowledgeStatus

    roster_entry = models.ForeignKey(
        RosterEntry,
        on_delete=models.CASCADE,
        related_name="codex_knowledge",
        help_text="Character (via roster entry) that has this knowledge.",
    )
    entry = models.ForeignKey(
        CodexEntry,
        on_delete=models.CASCADE,
        related_name="character_knowledge",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UNCOVERED,
    )
    learning_progress = models.PositiveIntegerField(
        default=0,
        help_text="Accumulated progress toward entry.learn_threshold.",
    )
    learned_from = models.ForeignKey(
        RosterTenure,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="codex_taught",
        help_text="Tenure who taught this entry.",
    )
    learned_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this entry was fully learned.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["roster_entry", "entry"]
        verbose_name = "Character Codex Knowledge"
        verbose_name_plural = "Character Codex Knowledge"

    def __str__(self) -> str:
        return f"{self.roster_entry}: {self.entry.name} ({self.status})"

    def add_progress(self, amount: int) -> bool:
        """
        Add learning progress and check for completion.

        Args:
            amount: Progress to add.

        Returns:
            True if learning completed, False otherwise.
        """
        if self.status != self.Status.UNCOVERED:
            return False

        self.learning_progress += amount
        if self.learning_progress >= self.entry.learn_threshold:
            self.status = self.Status.KNOWN
            self.learned_at = timezone.now()
            self.save(update_fields=["learning_progress", "status", "learned_at"])
            return True

        self.save(update_fields=["learning_progress"])
        return False

    def is_complete(self) -> bool:
        """Check if this knowledge is fully learned."""
        return self.status == self.Status.KNOWN


class CodexClue(NaturalKeyMixin, models.Model):
    """A clue that hints at the existence of a Codex entry and grants research progress."""

    entry = models.ForeignKey(
        CodexEntry,
        on_delete=models.CASCADE,
        related_name="clues",
        help_text="The entry this clue hints at.",
    )
    name = models.CharField(
        max_length=200,
        help_text="Name of the clue (e.g., 'Torn Journal Page').",
    )
    description = models.TextField(
        help_text="What the player sees when they find this clue.",
    )
    research_value = models.PositiveIntegerField(
        default=1,
        help_text="Research progress granted when this clue is found.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["entry", "name"]
        dependencies = ["codex.CodexEntry"]

    class Meta:
        unique_together = ["entry", "name"]
        verbose_name = "Codex Clue"
        verbose_name_plural = "Codex Clues"

    def __str__(self) -> str:
        return f"{self.name} -> {self.entry.name}"


class CharacterClueKnowledge(models.Model):
    """Tracks which clues a character has found (prevents duplicate research value)."""

    roster_entry = models.ForeignKey(
        RosterEntry,
        on_delete=models.CASCADE,
        related_name="clue_knowledge",
    )
    clue = models.ForeignKey(
        CodexClue,
        on_delete=models.CASCADE,
        related_name="character_knowledge",
    )
    found_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["roster_entry", "clue"]
        verbose_name = "Character Clue Knowledge"
        verbose_name_plural = "Character Clue Knowledge"

    def __str__(self) -> str:
        return f"{self.roster_entry}: found {self.clue.name}"


class CodexTeachingOffer(VisibilityMixin, models.Model):
    """
    A teaching offer from one player's tenure to others.

    Uses RosterTenure because teaching relationships belong to a player's
    time with a character - if a character changes hands, their teaching
    offers wouldn't make sense for the new player.

    Teacher pays AP upfront (banked). Offer persists indefinitely.
    Learner accepts, pays AP + optional gold, starts learning.
    Teacher can cancel to recover banked AP (capped at max).
    """

    teacher = models.ForeignKey(
        RosterTenure,
        on_delete=models.CASCADE,
        related_name="codex_teaching_offers",
        help_text="Tenure (player-character instance) offering to teach.",
    )
    entry = models.ForeignKey(
        CodexEntry,
        on_delete=models.CASCADE,
        related_name="teaching_offers",
    )
    pitch = models.TextField(
        help_text="Player-written description of what they're offering to teach.",
    )
    gold_cost = models.PositiveIntegerField(
        default=0,
        help_text="Optional gold payment required from learner.",
    )
    banked_ap = models.PositiveIntegerField(
        help_text="AP committed from teacher's pool.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Codex Teaching Offer"
        verbose_name_plural = "Codex Teaching Offers"

    def __str__(self) -> str:
        return f"{self.teacher} teaches {self.entry.name}"

    def cancel(self) -> int:
        """
        Cancel offer, return banked AP to teacher.

        Returns:
            Amount of AP actually restored to teacher's pool.
        """
        pool = ActionPointPool.get_or_create_for_character(self.teacher.character)
        restored = pool.unbank(self.banked_ap)
        self.delete()
        return restored

    def can_accept(self, learner: RosterTenure) -> tuple[bool, str]:
        """
        Check if learner can accept this offer.

        Returns:
            (can_accept, reason) tuple.
        """
        # Can't teach yourself
        if learner == self.teacher:
            return False, "Cannot accept your own teaching offer."

        # Check if character already knows or is learning
        existing = CharacterCodexKnowledge.objects.filter(
            roster_entry=learner.roster_entry,
            entry=self.entry,
        ).first()
        if existing:
            if existing.status == CharacterCodexKnowledge.Status.KNOWN:
                return False, "You already know this entry."
            return False, "You are already learning this entry."

        # Check prerequisites (character-level knowledge)
        prereq_ids = list(self.entry.prerequisites.values_list("id", flat=True))
        if prereq_ids:
            known_prereqs = CharacterCodexKnowledge.objects.filter(
                roster_entry=learner.roster_entry,
                entry_id__in=prereq_ids,
                status=CharacterCodexKnowledge.Status.KNOWN,
            ).count()
            if known_prereqs < len(prereq_ids):
                return False, "You don't meet the prerequisites for this entry."

        # Check AP - uses character from tenure
        pool = ActionPointPool.get_or_create_for_character(learner.character)
        if not pool.can_afford(self.entry.learn_cost):
            return False, "Insufficient action points."

        # TODO: Check gold when economy system exists

        return True, ""

    def accept(self, learner: RosterTenure) -> CharacterCodexKnowledge:
        """
        Learner accepts offer.

        Pays costs, creates knowledge entry, consumes teacher's banked AP.

        Returns:
            The new CharacterCodexKnowledge entry.

        Raises:
            ValueError: If learner cannot accept the offer.
        """
        can_accept, reason = self.can_accept(learner)
        if not can_accept:
            raise ValueError(reason)

        with transaction.atomic():
            # Learner pays AP - uses character from tenure
            learner_pool = ActionPointPool.get_or_create_for_character(learner.character)
            learner_pool.spend(self.entry.learn_cost)

            # Teacher's banked AP is consumed - uses character from tenure
            teacher_pool = ActionPointPool.get_or_create_for_character(self.teacher.character)
            teacher_pool.consume_banked(self.banked_ap)

            # Create knowledge entry (character-level, tracks who taught)
            # TODO: Transfer gold when economy system exists
            return CharacterCodexKnowledge.objects.create(
                roster_entry=learner.roster_entry,
                entry=self.entry,
                status=CharacterCodexKnowledge.Status.UNCOVERED,
                learned_from=self.teacher,
            )


# =============================================================================
# CG Grant Models
# =============================================================================


class BeginningsCodexGrant(NaturalKeyMixin, models.Model):
    """Codex entries granted by a Beginnings choice."""

    beginnings = models.ForeignKey(
        "character_creation.Beginnings",
        on_delete=models.CASCADE,
        related_name="codex_grants",
    )
    entry = models.ForeignKey(
        CodexEntry,
        on_delete=models.CASCADE,
        related_name="beginnings_grants",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["beginnings", "entry"]
        dependencies = ["character_creation.Beginnings", "codex.CodexEntry"]

    class Meta:
        unique_together = ["beginnings", "entry"]
        verbose_name = "Beginnings Codex Grant"
        verbose_name_plural = "Beginnings Codex Grants"

    def __str__(self) -> str:
        return f"{self.beginnings} grants {self.entry}"


class PathCodexGrant(NaturalKeyMixin, models.Model):
    """Codex entries granted by a Path choice."""

    path = models.ForeignKey(
        "classes.Path",
        on_delete=models.CASCADE,
        related_name="codex_grants",
    )
    entry = models.ForeignKey(
        CodexEntry,
        on_delete=models.CASCADE,
        related_name="path_grants",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["path", "entry"]
        dependencies = ["classes.Path", "codex.CodexEntry"]

    class Meta:
        unique_together = ["path", "entry"]
        verbose_name = "Path Codex Grant"
        verbose_name_plural = "Path Codex Grants"

    def __str__(self) -> str:
        return f"{self.path} grants {self.entry}"


class DistinctionCodexGrant(NaturalKeyMixin, models.Model):
    """Codex entries granted by a Distinction."""

    distinction = models.ForeignKey(
        "distinctions.Distinction",
        on_delete=models.CASCADE,
        related_name="codex_grants",
    )
    entry = models.ForeignKey(
        CodexEntry,
        on_delete=models.CASCADE,
        related_name="distinction_grants",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["distinction", "entry"]
        dependencies = ["distinctions.Distinction", "codex.CodexEntry"]

    class Meta:
        unique_together = ["distinction", "entry"]
        verbose_name = "Distinction Codex Grant"
        verbose_name_plural = "Distinction Codex Grants"

    def __str__(self) -> str:
        return f"{self.distinction} grants {self.entry}"


class TraditionCodexGrant(NaturalKeyMixin, models.Model):
    """Codex entries granted by a Tradition."""

    tradition = models.ForeignKey(
        "magic.Tradition",
        on_delete=models.CASCADE,
        related_name="codex_grants",
    )
    entry = models.ForeignKey(
        CodexEntry,
        on_delete=models.CASCADE,
        related_name="tradition_grants",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["tradition", "entry"]
        dependencies = ["magic.Tradition", "codex.CodexEntry"]

    class Meta:
        unique_together = ["tradition", "entry"]
        verbose_name = "Tradition Codex Grant"
        verbose_name_plural = "Tradition Codex Grants"

    def __str__(self) -> str:
        return f"{self.tradition} grants {self.entry}"
