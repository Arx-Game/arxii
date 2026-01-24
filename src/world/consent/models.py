"""
OOC Consent system models.

Simple player-controlled visibility groups for sharing content.
Separate from IC mechanical relationships.

Uses RosterTenure instead of ObjectDB because characters can change hands
between players - consent belongs to the player's tenure, not the character.
"""

from django.db import models

from world.roster.models import RosterTenure


class ConsentGroup(models.Model):
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


class ConsentGroupMember(models.Model):
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
