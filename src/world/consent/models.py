"""
OOC Consent system models.

Simple player-controlled visibility groups for sharing content.
Separate from IC mechanical relationships.

Uses RosterTenure instead of ObjectDB because characters can change hands
between players - consent belongs to the player's tenure, not the character.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.consent.constants import ConsentMode
from world.roster.models import RosterTenure


class ConsentGroup(SharedMemoryModel):
    """
    A custom group created by a player for consent/visibility purposes.

    Examples: "My Trusted Circle", "Scene Partners", "Guild Members"
    """

    owner = models.ForeignKey(
        RosterTenure,
        on_delete=models.CASCADE,
        related_name="consent_groups",
        help_text="Tenure (player-character instance) that owns this group.",
    )
    name = models.CharField(
        max_length=100,
        help_text="Name of this consent group.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["owner", "name"]
        verbose_name = "Consent Group"
        verbose_name_plural = "Consent Groups"

    def __str__(self) -> str:
        return f"{self.owner}: {self.name}"


class ConsentGroupMember(SharedMemoryModel):
    """Membership in a consent group."""

    group = models.ForeignKey(
        ConsentGroup,
        on_delete=models.CASCADE,
        related_name="members",
    )
    tenure = models.ForeignKey(
        RosterTenure,
        on_delete=models.CASCADE,
        related_name="consent_memberships",
        help_text="Tenure (player-character instance) that is a member.",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["group", "tenure"]
        verbose_name = "Consent Group Member"
        verbose_name_plural = "Consent Group Members"

    def __str__(self) -> str:
        return f"{self.tenure} in {self.group.name}"


class VisibilityMixin(models.Model):
    """
    Mixin for models that need OOC visibility control.

    Usage:
        class MyModel(VisibilityMixin, models.Model):
            # Your fields...
            pass

        # Check visibility:
        if my_instance.is_visible_to(viewer_tenure):
            # show content
    """

    class VisibilityMode(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"
        CHARACTERS = "characters", "Specific Characters"
        GROUPS = "groups", "Consent Groups"

    visibility_mode = models.CharField(
        max_length=20,
        choices=VisibilityMode.choices,
        default=VisibilityMode.PRIVATE,
        help_text="Who can see this content.",
    )
    visible_to_tenures = models.ManyToManyField(
        RosterTenure,
        blank=True,
        related_name="%(class)s_visible",
        help_text="Tenures who can see this (if mode is 'characters').",
    )
    visible_to_groups = models.ManyToManyField(
        ConsentGroup,
        blank=True,
        related_name="%(class)s_visible",
        help_text="Consent groups who can see this (if mode is 'groups').",
    )
    excluded_tenures = models.ManyToManyField(
        RosterTenure,
        blank=True,
        related_name="%(class)s_excluded",
        help_text="Tenures explicitly excluded even if otherwise visible.",
    )

    class Meta:
        abstract = True

    def is_visible_to(self, viewer: RosterTenure) -> bool:
        """
        Check if viewer can see this content.

        Visibility rules:
        - Excluded tenures are always blocked
        - PUBLIC: Everyone can see
        - PRIVATE: No one can see (except owner, handled by caller)
        - CHARACTERS: Only specified tenures
        - GROUPS: Only members of specified groups
        """
        # Exclusion always takes priority
        if self.excluded_tenures.filter(pk=viewer.pk).exists():
            return False

        if self.visibility_mode == self.VisibilityMode.PUBLIC:
            return True

        if self.visibility_mode == self.VisibilityMode.PRIVATE:
            return False

        if self.visibility_mode == self.VisibilityMode.CHARACTERS:
            return self.visible_to_tenures.filter(pk=viewer.pk).exists()

        if self.visibility_mode == self.VisibilityMode.GROUPS:
            return self.visible_to_groups.filter(members__tenure=viewer).exists()

        return False


class SocialConsentCategory(NaturalKeyMixin, SharedMemoryModel):
    """A data-driven kind of social action for consent purposes (#1141).

    Seeded rows (Romantic, Hostile, Manipulative, General). Staff add more
    without code changes. ActionTemplates are tagged with a category; players
    set per-category consent rules.
    """

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["key"]

    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Stable slug (e.g. 'romantic', 'hostile').",
    )
    name = models.CharField(max_length=100, help_text="Player-facing label.")
    description = models.TextField(blank=True, help_text="What this category covers.")
    display_order = models.PositiveIntegerField(
        default=0, help_text="Sort order in the consent UI."
    )
    default_mode = models.CharField(
        max_length=20,
        choices=ConsentMode.choices,
        default=ConsentMode.EVERYONE,
        help_text=(
            "Targeting mode when a player has set no rule for this category. "
            "EVERYONE preserves legacy behavior; ALLOWLIST makes the category "
            "opt-in (used by theft, #1909)."
        ),
    )

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Social Consent Category"
        verbose_name_plural = "Social Consent Categories"

    def __str__(self) -> str:
        return self.name


class SocialConsentPreference(SharedMemoryModel):
    """Per-tenure opt-out for social action targeting (#544, #1141).

    One row per RosterTenure (unique). Default: all social actions allowed.
    Per-category rules are stored in SocialConsentCategoryRule.
    """

    tenure = models.OneToOneField(
        RosterTenure,
        on_delete=models.CASCADE,
        related_name="social_consent_preference",
        help_text="One preference record per tenure.",
    )
    allow_social_actions = models.BooleanField(
        default=True,
        help_text="If False, this character never appears as a valid social action target.",
    )

    class Meta:
        verbose_name = "Social Consent Preference"
        verbose_name_plural = "Social Consent Preferences"

    def __str__(self) -> str:
        return f"SocialConsentPreference({self.tenure_id})"


class SocialConsentCategoryRule(SharedMemoryModel):
    """Per-category targeting mode for a tenure's consent preference (#1141).

    Absent row for a category == EVERYONE (default-allow).
    """

    preference = models.ForeignKey(
        SocialConsentPreference,
        on_delete=models.CASCADE,
        related_name="category_rules",
    )
    category = models.ForeignKey(
        SocialConsentCategory,
        on_delete=models.CASCADE,
        related_name="rules",
    )
    mode = models.CharField(
        max_length=20,
        choices=ConsentMode.choices,
        default=ConsentMode.EVERYONE,
        help_text=(
            "EVERYONE (anyone), ALL_BUT_BLACKLIST (anyone but this category's "
            "blacklist), FRIENDS_WHITELIST (OOC friends + whitelist), or "
            "ALLOWLIST (only whitelisted actors)."
        ),
    )

    class Meta:
        unique_together = ["preference", "category"]
        verbose_name = "Social Consent Category Rule"
        verbose_name_plural = "Social Consent Category Rules"

    def __str__(self) -> str:
        return f"{self.preference.tenure_id}:{self.category.key}={self.mode}"


class SocialConsentWhitelist(SharedMemoryModel):
    """Explicit whitelist entry: allowed_tenure may target owner_tenure socially (#544, #1141).

    Scoped per category; consulted when the owner's SocialConsentCategoryRule
    for a category is ALLOWLIST.
    """

    owner_tenure = models.ForeignKey(
        RosterTenure,
        on_delete=models.CASCADE,
        related_name="social_consent_whitelist_owned",
        help_text="Tenure that owns the preference (receives social actions).",
    )
    allowed_tenure = models.ForeignKey(
        RosterTenure,
        on_delete=models.CASCADE,
        related_name="social_consent_whitelist_allowed",
        help_text="Tenure permitted to target owner_tenure with social actions.",
    )
    category = models.ForeignKey(
        SocialConsentCategory,
        on_delete=models.CASCADE,
        related_name="whitelist_entries",
        help_text="Allowlist is scoped per category.",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["owner_tenure", "allowed_tenure", "category"]
        verbose_name = "Social Consent Whitelist Entry"
        verbose_name_plural = "Social Consent Whitelist Entries"

    def __str__(self) -> str:
        return (
            f"SocialConsentWhitelist({self.owner_tenure_id} ← "
            f"{self.allowed_tenure_id} [{self.category_id}])"
        )


class SocialConsentBlacklist(SharedMemoryModel):
    """Explicit antagonism blacklist: blocked_tenure may NOT target owner_tenure (#1698).

    Scoped per category; consulted when the owner's SocialConsentCategoryRule for a
    category is ALL_BUT_BLACKLIST. This is the "I'd rather not be antagonized by this
    specific person" surface — deliberately weaker than a scenes.Block (which severs all
    interaction): a blacklist only excludes the person from *this category's* social
    targeting, and the blocked party is never told.
    """

    owner_tenure = models.ForeignKey(
        RosterTenure,
        on_delete=models.CASCADE,
        related_name="social_consent_blacklist_owned",
        help_text="Tenure that owns the preference (does NOT want these actions).",
    )
    blocked_tenure = models.ForeignKey(
        RosterTenure,
        on_delete=models.CASCADE,
        related_name="social_consent_blacklist_blocked",
        help_text="Tenure barred from targeting owner_tenure in this category.",
    )
    category = models.ForeignKey(
        SocialConsentCategory,
        on_delete=models.CASCADE,
        related_name="blacklist_entries",
        help_text="Blacklist is scoped per category.",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["owner_tenure", "blocked_tenure", "category"]
        verbose_name = "Social Consent Blacklist Entry"
        verbose_name_plural = "Social Consent Blacklist Entries"

    def __str__(self) -> str:
        return (
            f"SocialConsentBlacklist({self.owner_tenure_id} ⊘ "
            f"{self.blocked_tenure_id} [{self.category_id}])"
        )
