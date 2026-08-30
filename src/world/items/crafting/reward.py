"""Crafting reward loop: a masterwork makes its maker a little famous (#2243).

Top-tier work is socially inert without this — quality only fed mechanical stat
modifiers. A masterwork craft now creates a solo ``LegendEntry`` (a deed) for the
crafter's persona, so fine work attaches to the maker's renown track record (the
"famous for forging the alaricite blade" fantasy). Magnitudes are PLACEHOLDER.

Lives crafting-side and imports the legend engine (items → societies is the
allowed direction; societies is the reusable renown primitive, ADR-0010).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.crafting.constants import (
    CRAFTING_FAME_ACCENT_WEIGHT,
    MASTERWORK_DEED_BASE_VALUE,
    MASTERWORK_STAT_MULTIPLIER_THRESHOLD,
)

if TYPE_CHECKING:
    from world.items.models import ItemInstance, QualityTier
    from world.scenes.models import Persona


def is_masterwork(tier: QualityTier | None) -> bool:
    """Whether a resolved quality tier counts as masterwork (#2243).

    Callers should pair this with an explicit ``tier is not None`` narrowing before
    passing ``tier`` on (a masterwork is never ``None``, but the type checker only
    narrows through the plain ``is not None`` check, not this predicate).
    """
    return tier is not None and tier.stat_multiplier >= MASTERWORK_STAT_MULTIPLIER_THRESHOLD


def crafting_deed_value(tier: QualityTier, accents: tuple | list = ()) -> int:
    """Fame magnitude for a first making (#2878, generalizes the #2243 threshold).

    ``base × (multiplier − 1) × (1 + weight × Σ accent rungs)``, floored to
    int. Work at or below baseline quality (multiplier ≤ 1) is worth 0 — the
    old hard masterwork threshold becomes emergent: unremarkable work simply
    isn't noteworthy, while quality and Accents scale fame continuously.
    PLACEHOLDER magnitudes.
    """
    over_baseline = float(tier.stat_multiplier) - 1.0
    if over_baseline <= 0:
        return 0
    accent_sum = sum(a.level.level for a in accents)
    return int(
        MASTERWORK_DEED_BASE_VALUE * over_baseline * (1 + CRAFTING_FAME_ACCENT_WEIGHT * accent_sum)
    )


def _working_was_perilous() -> bool:
    """Did this working put the maker's life at stake (#3463)?

    Always False today, and deliberately so rather than being inlined away: a
    perilous working is real and ruled in, but it reaches Legend through the
    stakes-contract settlement seam (``world.societies.legend_settlement``),
    not through this fame path, which has no contract to consult. This function
    is the named seam where a future crafting-under-stakes surface plugs in, so
    the "why does this always return False" question has an answer in place.
    """
    return False


def award_crafting_fame(  # noqa: PLR0913 — credit pair + scaling context
    *,
    crafter_persona: Persona | None,
    designer_persona: Persona | None,
    tier: QualityTier,
    accents: tuple | list = (),
    item_label: str = "",
    item_instance: ItemInstance | None = None,
) -> None:
    """Fame at first making, to BOTH crafter and designer personas (#2878).

        Persona-scoped (a masked artisan's fame accrues to the mask). Each
        credited persona gets a solo legend deed valued by ``crafting_deed_value``
        — zero-value work mints nothing. Deeds link to the item (#2359) so the
        piece's legend and its makers' fame stay one graph.

    **Mints nothing for safe work (#3463)** — see the comment in the body.
    """
    from world.societies.models import LegendSourceType  # noqa: PLC0415
    from world.societies.services import create_solo_deed  # noqa: PLC0415

    # #3463: an ordinary masterwork risks nothing, so it mints no Legend.
    # Ruled twice by Tehom (2026-08-29): "if it is not risky to you, the legend
    # should just be zero", and "perilous crafting and rites keep minting deeds
    # — if something is dangerous to *you*, then yes. It can give legend."
    #
    # Crafting is NOT excluded as a category. A working that genuinely could
    # have killed the forge crew settles through its stakes contract like
    # anything else, at a real station, and the piece carries THAT deed. This
    # function has no stakes context to consult, so it is the safe path by
    # definition and mints nothing.
    #
    # Consequence, stated rather than discovered later: ordinary masterworks
    # stop carrying item legend. ItemInstance.legend_deeds becomes rare and
    # meaningful instead of routine — a sword is legendary for what it cost to
    # make, not for being well made. ADR-0194 sharpened, not broken.
    #
    # crafting_deed_value() is deliberately KEPT and still called: it is the
    # sizing function a perilous working needs, and it remains the single place
    # that knows how quality and Accents scale a piece's worth. It is wired
    # here, not orphaned.
    value = crafting_deed_value(tier, accents)
    if value < 1 or not _working_was_perilous():
        return
    source_type, _ = LegendSourceType.objects.get_or_create(
        name="Crafting",
        defaults={"description": "Fine crafting — goods that make a name."},
    )
    seen_pks = set()
    for persona, verb in ((crafter_persona, "Crafted"), (designer_persona, "Designed")):
        if persona is None or persona.pk in seen_pks:
            continue
        seen_pks.add(persona.pk)
        entry = create_solo_deed(
            persona,
            f"{verb} a {tier.name.lower()} {item_label}".strip(),
            source_type,
            value,
            description=f"PLACEHOLDER — {tier.name}-quality work worthy of note.",
        )
        if item_instance is not None:
            item_instance.legend_deeds.add(entry)
