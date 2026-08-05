"""Forms-app-owned constants: check-type names and body-marking choices.

Check names mirror the sibling-app convention (``secrets.constants.GOSSIP_CHECK_TYPE_NAME``,
``items.constants.FASHION_PRESENTATION_CHECK_TYPE_NAME``): the app that owns a check's
domain owns the ``CheckType`` name constant, imported by its seed + its service module.
"""

from django.db import models

# The "recognize the person under the mask" check (#1107 slice 5) — intellect + Investigation.
# Seeded in ``world.seeds.investigation_checks.ensure_identification_check``. Deliberately NOT
# the "Search" CheckType (perception + Investigation, #1705) — wrong stat pairing per Apostate's
# 2026-07-03 ruling.
IDENTIFICATION_CHECK_TYPE_NAME = "Identification"


class MarkingKind(models.TextChoices):
    """Body-marking varieties (#2985).

    RUNE = magical inscription (resonance-touched, not mundane craft) — Apostate's
    2026-08-05 ruling replacing RITUAL_MARK: a ritual brand is a BRAND, a
    ceremonial tattoo a TATTOO; the distinguishing axis is magic.
    """

    TATTOO = "tattoo", "Tattoo"
    SCAR = "scar", "Scar"
    BRAND = "brand", "Brand"
    BIRTHMARK = "birthmark", "Birthmark"
    RUNE = "rune", "Rune"


class MarkingSource(models.TextChoices):
    """Provenance of a body marking (#2985) — the future combat/soulfray scar
    writers land as SYSTEM through the same ``grant_marking`` seam."""

    CHARGEN = "chargen", "Character Creation"
    GM_GRANT = "gm_grant", "GM Grant"
    SYSTEM = "system", "System"
