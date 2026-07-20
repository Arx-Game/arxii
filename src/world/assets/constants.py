"""Constants for the NPCAsset informant/contact promotion mechanic (#1872)."""

from __future__ import annotations

from django.db import models


class AssetAcquisitionSource(models.TextChoices):
    """How an NPCAsset was acquired.

    PROMOTION is the runtime path (a class-1 Functionary cultivated through
    interaction + a capability check, #1872). DISTINCTION_GRANT is the
    character-creation path (a starting asset granted by a Distinction, #1906).
    COERCION is the blackmail path (#1680): leverage over a sheeted NPC extracts
    them as a coerced asset — no functionary, no rapport, no capability check
    (unless the NPC is actively piloted, then the pilot resists like a player).
    """

    PROMOTION = "promotion", "Promotion"
    DISTINCTION_GRANT = "distinction_grant", "Distinction Grant"
    COERCION = "coercion", "Coercion"
    # #2295 — voluntary sharing: a PC introduces their asset to a co-present ally.
    INTRODUCTION = "introduction", "Introduction"
    # #2502 — charm-sourced acquisition: charmed NPC extracted as an asset.
    CHARM = "charm", "Charm"


class AssetRoleContext(models.TextChoices):
    """What kind of relationship a promoted NPCAsset serves."""

    INFORMANT = "informant", "Informant"
    CONTACT = "contact", "Contact"
    PERSONAL_FAVOR = "personal_favor", "Personal Favor"
    # #1907 — guard/fan/minor-ally asset role_context variants.
    GUARD = "guard", "Guard"
    FAN = "fan", "Fan"
    MINOR_ALLY = "minor_ally", "Minor Ally"


class AssetStatus(models.TextChoices):
    """Lifecycle state of an NPCAsset (#1905).

    Transitions are never GM fiat — they flow exclusively through the
    consequence pool system (ASSET_STATUS EffectType on ConsequenceEffect).
    Only COMPROMISED is recoverable (back to ACTIVE); LOST and DISMISSED
    are terminal.
    """

    ACTIVE = "active", "Active"
    COMPROMISED = "compromised", "Compromised"
    LOST = "lost", "Lost"
    DISMISSED = "dismissed", "Dismissed"


class AssetTransitionReason(models.TextChoices):
    """Structured cause for an asset status transition (#1905).

    Used as the ``reason`` parameter on ``transition_asset_status()`` so
    trigger handlers can filter on structured reason values in
    ``base_filter_condition`` rather than parsing free-form text.
    """

    CONSEQUENCE = "consequence", "Consequence pool fired"
    CHARACTER_KILLED = "character_killed", "Asset's character killed"
    PLAYER_DISMISSAL = "player_dismissal", "Player dismissed asset"
    RECOVERY = "recovery", "Asset recovered/rescued"
