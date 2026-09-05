"""
Codex system models.

Lore storage and character knowledge tracking. Characters can learn entries
from starting choices (Beginnings, Path, Distinctions) or through teaching.
"""

from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import connection, models, transaction
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from evennia_extensions.mixins import RelatedCacheClearingMixin
from world.achievements.models import DiscoverableContent
from world.action_points.models import ActionPointPool
from world.codex.constants import CodexKnowledgeStatus
from world.consent.models import VisibilityMixin
from world.contributors.models import CreditedContent
from world.roster.models import RosterEntry, RosterTenure

# Lazy model reference (Django app_label.ModelName), extracted to satisfy S1192.
CODEX_ENTRY_MODEL = "arxii.CodexEntry"


class CodexCategory(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        refresh_codex_breadcrumbs()


class CodexSubject(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
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
        dependencies = ["arxii.CodexCategory"]

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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        refresh_codex_breadcrumbs()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        refresh_codex_breadcrumbs()
        return result


class CodexSubjectBreadcrumb(SharedMemoryModel):
    """Read-only model backed by a Postgres materialized view.

    Pre-computes the full breadcrumb path for every CodexSubject as a JSONB array.
    Refreshed when subjects or categories are saved/deleted.
    """

    subject = models.OneToOneField(
        CodexSubject, on_delete=models.DO_NOTHING, related_name="breadcrumb_cache"
    )
    breadcrumb_path = models.JSONField()

    class Meta:
        managed = False
        db_table = "codex_subjectbreadcrumb"


def refresh_codex_breadcrumbs() -> None:
    """Refresh the codex_subjectbreadcrumb materialized view."""
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW codex_subjectbreadcrumb")


class CodexEntry(NaturalKeyMixin, CreditedContent, DiscoverableContent, SharedMemoryModel):
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
    is_featured = models.BooleanField(
        default=False,
        help_text="If True, included in the curated onboarding lore shown on "
        "the front page and linked from CG stages. Requires is_public=True.",
    )
    featured_order = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Display order for featured entries (1, 2, 3...). NULL for non-featured.",
    )
    modifier_target = models.OneToOneField(
        "arxii.ModifierTarget",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="codex_entry",
        help_text="Link to a modifier target this entry documents (for resonances, stats, etc.).",
    )
    art = models.ForeignKey(
        "arxii.Media",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="codex_entries",
        help_text="Illustration for this entry, shown in the codex modal (#2408).",
    )
    subject_item_template = models.ForeignKey(
        "arxii.ItemTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="codex_entries_about",
        help_text=(
            "The item kind this entry is about, if any (#2540 exact-pointer ruling). "
            "Template-only means 'any of this kind'; see subject_item_instance for the "
            "narrower 'this exact one' pointer."
        ),
    )
    subject_item_instance = models.ForeignKey(
        "arxii.ItemInstance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="codex_entries_about",
        help_text=(
            "Optional exact instance this entry is about (#2540), narrowing "
            "subject_item_template. SET_NULL so a destroyed instance degrades the "
            "entry to template-only rather than deleting it."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["subject", "name"]
        dependencies = ["arxii.CodexSubject"]

    class Meta:
        ordering = ["display_order", "name"]
        unique_together = ["subject", "name"]
        verbose_name = "Codex Entry"
        verbose_name_plural = "Codex Entries"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """Validate content fields and featured/public consistency."""
        super().clean()
        if not self.lore_content and not self.mechanics_content:
            msg = "At least one of lore_content or mechanics_content must be provided."
            raise ValidationError(msg)
        if self.is_featured and not self.is_public:
            msg = "A featured entry must also be public (is_public=True)."
            raise ValidationError({"is_featured": msg})
        if (
            self.subject_item_instance_id is not None
            and self.subject_item_template_id is not None
            and self.subject_item_instance.template_id != self.subject_item_template_id
        ):
            msg = "Must be an instance of subject_item_template when both are set."
            raise ValidationError({"subject_item_instance": msg})


class CodexEntryFiling(NaturalKeyMixin, SharedMemoryModel):
    """A secondary listing of a CodexEntry under a subject other than its home.

    ``CodexEntry.subject`` stays the entry's one canonical home: its detail
    page lives there, and same-subject preference in ``resolve_codex_links``
    wikilink resolution is keyed off it. A filing cross-lists the entry under
    one additional subject's listing without moving it or duplicating its
    content - the entry is still fetched, edited, and rendered from the single
    row on ``CodexEntry``. See ADR-0270 for why this stays a dedicated link
    table rather than a many-to-many on either side.
    """

    entry = models.ForeignKey(
        CodexEntry,
        on_delete=models.CASCADE,
        related_name="filings",
    )
    subject = models.ForeignKey(
        CodexSubject,
        on_delete=models.CASCADE,
        related_name="filed_entries",
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Order for display within the filed subject's listing.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["entry", "subject"]
        dependencies = [CODEX_ENTRY_MODEL, "arxii.CodexSubject"]

    class Meta:
        ordering = ["subject", "sort_order", "pk"]
        unique_together = ["entry", "subject"]
        verbose_name = "Codex Entry Filing"
        verbose_name_plural = "Codex Entry Filings"

    def __str__(self) -> str:
        return f"{self.entry} filed under {self.subject}"


class CharacterCodexKnowledge(RelatedCacheClearingMixin, SharedMemoryModel):
    """
    Tracks what a character knows or is learning.

    Uses RosterEntry because knowledge belongs to the character itself -
    if a character changes hands, the new player inherits what the
    character knows.

    Learning progress tracks accumulated progress toward threshold,
    not ticks remaining (allows for variable/chance-based advancement).
    """

    # A knowledge write must clear the playing account's ``cached_codex_knowledge``
    # (#3597). The walk stops (getattr default None) when the character has no
    # current tenure; the next tenure save clears the account anyway.
    related_cache_fields: ClassVar[list[str]] = ["roster_entry.current_tenure.player_data.account"]

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
        choices=CodexKnowledgeStatus.choices,
        default=CodexKnowledgeStatus.UNCOVERED,
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
            True if learning completed (status transitioned to KNOWN),
            False otherwise.

        On the KNOWN transition this fires the stories reactivity hook, so
        CODEX_ENTRY_UNLOCKED beats re-evaluate no matter which caller landed
        the progress (#939 — a separate service wrapper used to carry the
        hook and every caller bypassed it; reactivity now lives on the only
        path).
        """
        if self.status != CodexKnowledgeStatus.UNCOVERED:
            return False

        self.learning_progress += amount
        if self.learning_progress >= self.entry.learn_threshold:
            self.status = CodexKnowledgeStatus.KNOWN
            self.learned_at = timezone.now()
            self.save(update_fields=["learning_progress", "status", "learned_at"])
            self._notify_stories_unlocked()
            return True

        self.save(update_fields=["learning_progress"])
        return False

    def _notify_stories_unlocked(self) -> None:
        """Fire the stories reactivity hook on the KNOWN transition.

        Lazy cross-app import keeps codex decoupled at module load time.
        """
        from world.stories.services.reactivity import on_codex_entry_unlocked  # noqa: PLC0415

        sheet = self.roster_entry.character_sheet
        if sheet is not None:
            on_codex_entry_unlocked(sheet, self.entry)

    def is_complete(self) -> bool:
        """Check if this knowledge is fully learned."""
        return self.status == CodexKnowledgeStatus.KNOWN


class CodexTeachingOffer(VisibilityMixin, SharedMemoryModel):
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
            if existing.status == CodexKnowledgeStatus.KNOWN:
                return False, "You already know this entry."
            return False, "You are already learning this entry."

        # Check prerequisites (character-level knowledge)
        prereq_ids = list(self.entry.prerequisites.values_list("id", flat=True))
        if prereq_ids:
            known_prereqs = CharacterCodexKnowledge.objects.filter(
                roster_entry=learner.roster_entry,
                entry_id__in=prereq_ids,
                status=CodexKnowledgeStatus.KNOWN,
            ).count()
            if known_prereqs < len(prereq_ids):
                return False, "You don't meet the prerequisites for this entry."

        # Check AP - uses character from tenure
        pool = ActionPointPool.get_or_create_for_character(learner.character)
        if not pool.can_afford(self.entry.learn_cost):
            return False, "Insufficient action points."

        # TODO: Check gold when economy system exists

        return True, ""

    def accept(self, learner: RosterTenure, *, room_profile=None) -> CharacterCodexKnowledge:
        """
        Learner accepts offer.

        Pays costs, creates knowledge entry, consumes teacher's banked AP.

        Args:
            learner: The tenure of the learner accepting the offer.
            room_profile: Optional RoomProfile of the learner's current room.
                When provided, an active Library feature in that room discounts
                the learner's AP cost (#675).

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
            learn_cost = self.entry.learn_cost
            if room_profile is not None:
                from world.codex.constants import LIBRARY_AP_DISCOUNT_PER_LEVEL  # noqa: PLC0415
                from world.room_features.services import active_library_in  # noqa: PLC0415

                library = active_library_in(room_profile)
                if library is not None:
                    learn_cost = max(1, learn_cost - library.level * LIBRARY_AP_DISCOUNT_PER_LEVEL)
            learner_pool.spend(learn_cost)

            # Teacher's banked AP is consumed - uses character from tenure
            teacher_pool = ActionPointPool.get_or_create_for_character(self.teacher.character)
            teacher_pool.consume_banked(self.banked_ap)

            # Create knowledge entry (character-level, tracks who taught)
            # TODO: Transfer gold when economy system exists
            return CharacterCodexKnowledge.objects.create(
                roster_entry=learner.roster_entry,
                entry=self.entry,
                status=CodexKnowledgeStatus.UNCOVERED,
                learned_from=self.teacher,
            )


# =============================================================================
# CG Grant Models
# =============================================================================


class BeginningsCodexGrant(NaturalKeyMixin, SharedMemoryModel):
    """Codex entries granted by a Beginnings choice.

    A row with ``is_perspective=True`` additionally marks the entry as this
    culture's own take on its subject (attribution surfaces as
    ``perspective_of`` on the entry API); at most one row per entry may claim
    it (#3277). That single-holder rule spans this table and
    ``TraditionCodexGrant`` together - an entry has at most one perspective
    holder overall, enforced across tables by ``clean()`` (#3281).
    """

    beginnings = models.ForeignKey(
        "arxii.Beginnings",
        on_delete=models.CASCADE,
        related_name="codex_grants",
    )
    entry = models.ForeignKey(
        CodexEntry,
        on_delete=models.CASCADE,
        related_name="beginnings_grants",
    )
    is_perspective = models.BooleanField(
        default=False,
        help_text="This entry is the granting culture's own take on its subject, "
        "written in that culture's voice, rather than canon-neutral knowledge "
        "it happens to teach (#3277).",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["beginnings", "entry"]
        dependencies = ["arxii.Beginnings", CODEX_ENTRY_MODEL]

    class Meta:
        unique_together = ["beginnings", "entry"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry"],
                condition=models.Q(is_perspective=True),
                name="one_perspective_holder_per_entry",
            ),
        ]
        verbose_name = "Beginnings Codex Grant"
        verbose_name_plural = "Beginnings Codex Grants"

    def clean(self) -> None:
        """The partial unique constraints are per-table; enforce one holder across tables."""
        super().clean()
        if self.is_perspective and (
            TraditionCodexGrant.objects.filter(entry=self.entry, is_perspective=True).exists()
        ):
            msg = (
                "This entry already has a tradition perspective holder; an entry has "
                "at most one perspective holder across all holder types."
            )
            raise ValidationError(msg)

    def __str__(self) -> str:
        return f"{self.beginnings} grants {self.entry}"


# Idmapper metaclass sets attrs["path"] which shadows the "path" FK
class PathCodexGrant(NaturalKeyMixin, models.Model):  # noqa: SHARED_MEMORY
    """Codex entries granted by a Path choice."""

    path = models.ForeignKey(
        "arxii.Path",
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
        dependencies = ["arxii.Path", CODEX_ENTRY_MODEL]

    class Meta:
        unique_together = ["path", "entry"]
        verbose_name = "Path Codex Grant"
        verbose_name_plural = "Path Codex Grants"

    def __str__(self) -> str:
        return f"{self.path} grants {self.entry}"


class DistinctionCodexGrant(NaturalKeyMixin, SharedMemoryModel):
    """Codex entries granted by a Distinction."""

    distinction = models.ForeignKey(
        "arxii.Distinction",
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
        dependencies = ["arxii.Distinction", CODEX_ENTRY_MODEL]

    class Meta:
        unique_together = ["distinction", "entry"]
        verbose_name = "Distinction Codex Grant"
        verbose_name_plural = "Distinction Codex Grants"

    def __str__(self) -> str:
        return f"{self.distinction} grants {self.entry}"


class TraditionCodexGrant(NaturalKeyMixin, SharedMemoryModel):
    """Codex entries granted by a Tradition.

    A row with ``is_perspective=True`` additionally marks the entry as this
    tradition's own take on its subject, written in that tradition's voice;
    at most one row per entry may claim it. That single-holder rule spans
    this table and ``BeginningsCodexGrant`` together - an entry has at most
    one perspective holder overall, enforced across tables by ``clean()``
    (#3281).
    """

    tradition = models.ForeignKey(
        "arxii.Tradition",
        on_delete=models.CASCADE,
        related_name="codex_grants",
    )
    entry = models.ForeignKey(
        CodexEntry,
        on_delete=models.CASCADE,
        related_name="tradition_grants",
    )
    is_perspective = models.BooleanField(
        default=False,
        help_text="This entry is the granting tradition's own take on its subject, "
        "written in that tradition's voice, rather than canon-neutral knowledge "
        "it happens to teach (#3281).",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["tradition", "entry"]
        dependencies = ["arxii.Tradition", CODEX_ENTRY_MODEL]

    class Meta:
        unique_together = ["tradition", "entry"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry"],
                condition=models.Q(is_perspective=True),
                name="one_tradition_perspective_holder_per_entry",
            ),
        ]
        verbose_name = "Tradition Codex Grant"
        verbose_name_plural = "Tradition Codex Grants"

    def clean(self) -> None:
        """The partial unique constraints are per-table; enforce one holder across tables."""
        super().clean()
        if self.is_perspective and (
            BeginningsCodexGrant.objects.filter(entry=self.entry, is_perspective=True).exists()
        ):
            msg = (
                "This entry already has a beginnings perspective holder; an entry has "
                "at most one perspective holder across all holder types."
            )
            raise ValidationError(msg)

    def __str__(self) -> str:
        return f"{self.tradition} grants {self.entry}"
