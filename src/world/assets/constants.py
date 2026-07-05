"""Constants for the NPCAsset informant/contact promotion mechanic (#1872)."""

from __future__ import annotations

from django.db import models


class AssetRoleContext(models.TextChoices):
    """What kind of relationship a promoted NPCAsset serves."""

    INFORMANT = "informant", "Informant"
    CONTACT = "contact", "Contact"
    PERSONAL_FAVOR = "personal_favor", "Personal Favor"
    # Future kinds (deferred — guard/fan/minor-ally variants, #1872 follow-up):
    # GUARD, FAN, MINOR_ALLY.


class AssetStatus(models.TextChoices):
    """Lifecycle state of an NPCAsset. Only ACTIVE is wired in this PR.

    COMPROMISED/LOST/DISMISSED are reserved names for the asset
    compromise/loss-lifecycle follow-up — declaring them now would be dead
    code with nothing to ever set them.
    """

    ACTIVE = "active", "Active"
