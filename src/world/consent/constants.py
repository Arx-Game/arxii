"""Consent system constants."""

from django.db import models


class ConsentMode(models.TextChoices):
    """Who may target a character with a given social-action category."""

    EVERYONE = "everyone", "Everyone"
    ALLOWLIST = "allowlist", "Allowlist only"
