"""Sun sensitivity tiers (#2846) — distinction-anchored, tag-identified.

The two Distinction rows (``Bane: Sunlight`` / ``Allergy: Sunlight``) are the
single mechanical anchor for sun vulnerability. Species stamp them innately
through ``SpeciesGiftGrant.drawback_distinction``; any other species may take
one voluntarily in CG for reimbursement. Both paths resolve here identically,
by ``DistinctionTag`` (the #2752 tag-not-hardcoded-slug pattern) — worst held
tier wins.
"""

from __future__ import annotations

from django.db import models

from world.species.sun_constants import (
    ALLERGY_GRACE,
    BANE_MINIMUM_SEVERITY,
    BANE_SEVERITY_SHIFT,
    SHADOW_CLEAR_THRESHOLD,
    SUN_ALLERGY_TAG,
    SUN_BANE_TAG,
)
from world.species.sun_exposure import SunExposure


class SunSensitivity(models.TextChoices):
    """How harshly residual sun exposure maps onto a character."""

    NONE = "none", "None"
    ALLERGY = "allergy", "Allergy"
    BANE = "bane", "Bane"


def sun_sensitivity_for(sheet) -> SunSensitivity:
    """The worst sun-sensitivity tier among *sheet*'s held distinctions."""
    if sheet is None:
        return SunSensitivity.NONE
    slugs = set(
        sheet.distinctions.filter(
            distinction__tags__slug__in=(SUN_BANE_TAG, SUN_ALLERGY_TAG),
        ).values_list("distinction__tags__slug", flat=True)
    )
    if SUN_BANE_TAG in slugs:
        return SunSensitivity.BANE
    if SUN_ALLERGY_TAG in slugs:
        return SunSensitivity.ALLERGY
    return SunSensitivity.NONE


def sun_severity(tier: SunSensitivity, exposure: SunExposure) -> int:
    """Map a tier + exposure breakdown to a target condition severity.

    Bane rides a floor: while shade alone leaves meaningful sun
    (``shade_only_residual`` above ``SHADOW_CLEAR_THRESHOLD``), a bane-tier
    character never drops below ``BANE_MINIMUM_SEVERITY`` — clothing and magic
    stop the *damage*, but only real shadow clears the debuff. Allergy has no
    floor and shrugs off ``ALLERGY_GRACE`` residual before feeling anything.
    """
    if tier == SunSensitivity.NONE or exposure.base <= 0:
        return 0
    if tier == SunSensitivity.BANE:
        if exposure.shade_only_residual <= SHADOW_CLEAR_THRESHOLD:
            return 0
        return max(BANE_MINIMUM_SEVERITY, exposure.residual + BANE_SEVERITY_SHIFT)
    return max(0, exposure.residual - ALLERGY_GRACE)
