"""Baseline area laws (#2862 gap close) — so crime finally costs something.

``AreaLaw`` has always been read by the justice pipeline and never written by
anything: no rows anywhere meant ``law_for`` returned None for every crime in
every area, which reads as "not a crime here". The consequence was total —
fenced contraband, mission crime-watch lines, murder deeds, theft: all minted
exactly zero heat on a fresh database, so the whole enforcement loop was inert.

This seeds one conservative default set at the reserved top-level area. Laws
cascade most-specific-wins, so authoring a neighborhood row later overrides
these without touching them, and an ``exempts`` row makes something locally
legal (a docks ward that shrugs at Haze). Weights are PLACEHOLDER: they set
relative severity, not final tuning.

Deliberately NOT a claim about the setting's justice: it is the minimum that
makes the built machinery observable. Real per-realm law is world data and
ApostateCD's to author.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

BASELINE_AREA_SLUG = "arx"

#: (crime slug, heat weight) — relative severity, PLACEHOLDER magnitudes.
_BASELINE_LAWS: tuple[tuple[str, int], ...] = (
    # Against persons — the heaviest.
    ("murder", 40),
    ("abduction", 30),
    ("assault-upon-the-gentle", 25),
    ("common-battery", 10),
    # Against property.
    ("arson", 30),
    ("robbery", 20),
    ("burglary", 15),
    ("theft", 10),
    ("receiving-stolen-goods", 8),
    # Trade and vice — the underworld's bread and butter (#2862). Moderate on
    # purpose: dealing is a living, not a hanging, and turf posture is meant to
    # move it.
    ("smuggling", 12),
    ("contraband", 10),
    # Crown and coin.
    ("treason", 50),
    ("sedition", 30),
    ("forgery", 15),
    ("tax-fraud", 15),
    ("bribery", 12),
    ("false-accusation", 12),
    ("evidence-tampering", 15),
)


def seed_baseline_area_laws() -> None:
    """Seed the baseline law set at the reserved top area (idempotent).

    Never overwrites an existing row — an authored or staff-tuned law wins.
    """
    from world.areas.models import Area  # noqa: PLC0415
    from world.justice.models import AreaLaw, CrimeKind  # noqa: PLC0415

    area = Area.objects.filter(slug=BASELINE_AREA_SLUG).first()
    if area is None:
        logger.warning(
            "Baseline area %r not found; area laws not seeded. Crime will mint "
            "no heat until laws are authored.",
            BASELINE_AREA_SLUG,
        )
        return
    seeded = 0
    for slug, weight in _BASELINE_LAWS:
        crime = CrimeKind.objects.filter(slug=slug).first()
        if crime is None:
            continue
        _row, created = AreaLaw.objects.get_or_create(
            area=area,
            crime_kind=crime,
            defaults={"heat_weight": weight, "exempts": False},
        )
        seeded += int(created)
    logger.info("Baseline area laws seeded: %d new rows at %s.", seeded, area)
