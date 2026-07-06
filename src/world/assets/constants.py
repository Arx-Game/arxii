"""Constants for the NPCAsset informant/contact promotion mechanic (#1872)."""

from __future__ import annotations

from django.db import models


class AssetAcquisitionSource(models.TextChoices):
    """How an NPCAsset was acquired.

    PROMOTION is the runtime path (a class-1 Functionary cultivated through
    interaction + a capability check, #1872). DISTINCTION_GRANT is the
    character-creation path (a starting asset granted by a Distinction, #1906).
    """

    PROMOTION = "promotion", "Promotion"
    DISTINCTION_GRANT = "distinction_grant", "Distinction Grant"


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
