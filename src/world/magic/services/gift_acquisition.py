"""Post-CG gift acquisition services (#1587).

spend_xp_on_gift_unlock: the XP gate (ADR-0053 — gate removal only).
accept_technique_offer: the acquisition step (implicitly acquires the
gift on the first technique learned from it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.models import GiftAcquisitionConfig

if TYPE_CHECKING:
    pass


def get_gift_acquisition_config() -> GiftAcquisitionConfig:
    """Lazily create and return the singleton GiftAcquisitionConfig (pk=1)."""
    config, _ = GiftAcquisitionConfig.objects.get_or_create(pk=1)
    return config
