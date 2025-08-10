"""
Type definitions for character sheets app.
"""

from django.db import models


class MaritalStatus(models.TextChoices):
    """Marital status choices for characters."""

    SINGLE = "single", "Single"
    MARRIED = "married", "Married"
    WIDOWED = "widowed", "Widowed"
    DIVORCED = "divorced", "Divorced"


class Gender(models.TextChoices):
    """Gender choices for characters."""

    MALE = "male", "Male"
    FEMALE = "female", "Female"
    NON_BINARY = "non_binary", "Non-Binary"
    OTHER = "other", "Other"
