"""Lookups for the acute-peril conditions staff designate in admin (#4739).

Bleeding Out, Plummeting and Surrounded are found through
``VitalsConsequenceConfig``, never by name, so renaming a template changes nothing.
Each lookup returns the designated template's primary key, or ``None`` when no
config row exists or the field is unset; a filter on ``condition_id=None`` then
matches no row. The Required content dashboard lists an unset designation.
"""

from __future__ import annotations

from world.vitals.models import VitalsConsequenceConfig


def _config() -> VitalsConsequenceConfig | None:
    return VitalsConsequenceConfig.objects.cached_singleton()


def bleed_out_condition_id() -> int | None:
    """Primary key of the condition template that IS Bleeding Out, or ``None``."""
    config = _config()
    return None if config is None else config.bleed_out_condition_id


def plummeting_condition_id() -> int | None:
    """Primary key of the condition template that IS Plummeting, or ``None``."""
    config = _config()
    return None if config is None else config.plummeting_condition_id


def surrounded_condition_id() -> int | None:
    """Primary key of the condition template that IS Surrounded, or ``None``."""
    config = _config()
    return None if config is None else config.surrounded_condition_id
