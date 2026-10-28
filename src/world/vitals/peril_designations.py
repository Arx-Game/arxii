"""Lookups for the acute-peril conditions staff designate in admin (#4739).

Bleeding Out, Plummeting and Surrounded are found through
``VitalsConsequenceConfig``, never by name, so renaming a template changes nothing.
Each lookup returns the designated template's primary key, or ``None`` when no
config row exists or the field is unset; the mechanic then does nothing and the
Required content dashboard lists the unset designation. Guard on ``None`` before
filtering a nullable column by one of these: ``filter(x_id=None)`` is ``IS NULL``
and matches every unset row. An ``__in`` list drops ``None`` safely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.vitals.models import VitalsConsequenceConfig

if TYPE_CHECKING:
    from world.conditions.models import ConditionTemplate


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


def plummeting_template() -> ConditionTemplate | None:
    """The condition template that IS Plummeting, or ``None`` when unset."""
    config = _config()
    return None if config is None else config.plummeting_condition


def surrounded_template() -> ConditionTemplate | None:
    """The condition template that IS Surrounded, or ``None`` when unset."""
    config = _config()
    return None if config is None else config.surrounded_condition


def designate_unset_peril_conditions(
    *,
    bleed_out: ConditionTemplate | None = None,
    plummeting: ConditionTemplate | None = None,
    surrounded: ConditionTemplate | None = None,
) -> None:
    """Point each unset acute-peril designation at the template a seed just made (#4739).

    For the bootstrap seeds and test factories that create these templates. A
    designation staff already set is never overwritten (precedent: the Soulfray seed).
    The config row is made lazily, as ``get_vitals_consequence_config`` always does.
    """
    from world.vitals.services import get_vitals_consequence_config  # noqa: PLC0415

    config = get_vitals_consequence_config()
    changed: list[str] = []
    if bleed_out is not None and config.bleed_out_condition_id is None:
        config.bleed_out_condition = bleed_out
        changed.append("bleed_out_condition")
    if plummeting is not None and config.plummeting_condition_id is None:
        config.plummeting_condition = plummeting
        changed.append("plummeting_condition")
    if surrounded is not None and config.surrounded_condition_id is None:
        config.surrounded_condition = surrounded
        changed.append("surrounded_condition")
    if changed:
        config.save(update_fields=changed)
