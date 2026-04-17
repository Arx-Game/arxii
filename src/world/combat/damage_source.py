"""Classify the origin of damage for reactive payloads.

Uses ``DamageSource`` from ``flows.events.payloads`` as the single source of truth.
``classify_source`` performs isinstance dispatch and returns a populated DamageSource.
"""

from flows.events.payloads import DamageSource


def classify_source(source: object | None) -> DamageSource:
    """Return a ``DamageSource`` describing *source*'s origin.

    Uses isinstance dispatch.  Unknown sources collapse to type='unknown'.
    Note: ``DamageSource.type`` is a Literal that does not include 'unknown';
    we use 'environment' as the fallback to stay within the defined union.
    """
    if source is None:
        return DamageSource(type="environment", ref=None)

    # Character dispatch (DefaultCharacter covers all Evennia character typeclasses)
    try:
        from evennia.objects.objects import DefaultCharacter  # noqa: PLC0415

        if isinstance(source, DefaultCharacter):
            return DamageSource(type="character", ref=source)
    except ImportError:
        pass

    # Technique dispatch
    try:
        from world.magic.models import Technique  # noqa: PLC0415

        if isinstance(source, Technique):
            return DamageSource(type="technique", ref=source)
    except ImportError:
        pass

    # Scar/ConditionInstance dispatch
    try:
        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        if isinstance(source, ConditionInstance):
            return DamageSource(type="scar", ref=source)
    except ImportError:
        pass

    # Fallback: unknown origin, but keep the ref so callers can inspect it
    return DamageSource(type="item", ref=source)
