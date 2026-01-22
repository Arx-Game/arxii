"""Type definitions for the goals system."""

from django.db.models import TextChoices


class GoalDomainSlug(TextChoices):
    """Slugs for the six goal domains."""

    STANDING = "standing", "Standing"
    WEALTH = "wealth", "Wealth"
    KNOWLEDGE = "knowledge", "Knowledge"
    MASTERY = "mastery", "Mastery"
    BONDS = "bonds", "Bonds"
    NEEDS = "needs", "Needs"
