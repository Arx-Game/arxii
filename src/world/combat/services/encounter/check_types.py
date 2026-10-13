"""Penetration and concentration check-type lookups."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import CONCENTRATION_CHECK_TYPE_NAME, PENETRATION_CHECK_TYPE_NAME

if TYPE_CHECKING:
    from world.checks.models import CheckType


def get_penetration_check_type() -> CheckType:
    """Return the seeded 'penetration' CheckType for the ward contest (#639).

    Uses get() — never get_or_create — because this is authored content; a
    chartless fabricated row would silently break the resolution pipeline.
    If the seed is missing, CheckType.DoesNotExist propagates loudly (a real
    misconfiguration), not masked. Mirrors
    ``_get_endure_hallowed_ground_check_type``.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    return CheckType.objects.get(name=PENETRATION_CHECK_TYPE_NAME)


def get_concentration_check_type() -> CheckType:
    """Return the seeded 'Concentration' CheckType rolled at sustained-action
    declaration (#2705).

    Uses get() — never get_or_create — because this is authored content; a
    chartless fabricated row would silently break the resolution pipeline.
    If the seed is missing, CheckType.DoesNotExist propagates loudly (a real
    misconfiguration), not masked. Mirrors ``get_penetration_check_type``.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    return CheckType.objects.get(name=CONCENTRATION_CHECK_TYPE_NAME)
