"""Seed the distinctive-physical-feature distinctions and their offers (#3739).

Four rows, all ``taken_per_feature`` — held once per feature (a trait row or a
marking), not once per character:

* **Make It Distinctive** (``opens_feature``, 1 point, rank 1) — the whole gate.
  Taking it on a feature opens that feature's description, widens its palette to
  every option the trait carries including the off-species Unnatural umbrella
  (a strange colour is assumed to have a magical explanation), and opens the
  three axis rows below it.
* **Alluring / Menacing / Regal** (``requires_feature_opened``, 2 points a tier,
  ``+_AXIS_PER_TIER`` to the axis a tier) — bought on an already-distinctive
  feature, in any combination: one scar can be all three. They reach rank 5 in
  play and stop at ``_CG_MAX_RANK`` in character creation, which is what
  ``cg_max_rank`` says.

The axes are the same three ``ModifierTarget`` rows item accents use (#2886), so
a feature and a garment push on the same number: allure through the directed-
allure engine, menace through Intimidation, regal through the Command check
(#3739, ``world.seeds.governance_checks``). A feature is worth more than a
garment on purpose — an accent rung is +1, a feature tier is +2.

Every row goes through ``authored_or_sample``: content-repo-owned (#2698),
invented here only under ``SEED_SAMPLE_CONTENT`` so a fresh clone has a walkable
Appearance stage. Prose is PLACEHOLDER; the catalogue pass is the maintainer's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.character_creation.constants import OfferArrival, OfferChapter

if TYPE_CHECKING:
    from world.distinctions.models import Distinction

#: What one tier of an axis adds to it. Item accents add +1 a rung (#2886); a
#: physical feature is meant to matter more than a worn thing, so it adds +2.
_AXIS_PER_TIER = 2

#: What one tier of an axis costs in CG points.
_AXIS_COST_PER_TIER = 2

#: The rank an axis reaches in play, and the ceiling character creation applies.
#: You may start distinctive; you may not start unforgettable.
_AXIS_MAX_RANK = 5
_AXIS_CG_MAX_RANK = 3

#: The one-point pick that makes a feature distinctive.
_OPENER_COST = 1

#: (slug, name, accent target, player line). The accent target is the
#: ``ModifierTarget`` the tier value lands on; each is seeded elsewhere
#: (``allure`` by ``social_relationships``, ``menace``/``regal`` by
#: ``crafting_materials``) and skipped here when a clone has none.
_AXES: tuple[tuple[str, str, str, str], ...] = (
    (
        "alluring-feature",
        "Alluring",
        "allure",
        "PLACEHOLDER: this feature is the one people cannot look away from.",
    ),
    (
        "menacing-feature",
        "Menacing",
        "menace",
        "PLACEHOLDER: this feature is the one people flinch from.",
    ),
    (
        "regal-feature",
        "Regal",
        "regal",
        "PLACEHOLDER: this feature is the one people take orders from.",
    ),
)

_OPENER_SLUG = "make-it-distinctive"


def _feature_category():
    """The category the feature rows sit in: Physical. Content-repo-owned (#2698)."""
    from world.distinctions.models import DistinctionCategory  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    return authored_or_sample(
        DistinctionCategory,
        {"name": "Physical", "description": "Body, bearing, and what people see."},
        slug="physical",
    )


def _ensure_offer(distinction: Distinction, sort_order: int) -> None:
    """Give ``distinction`` its Appearance feature-rows offer line (#3739).

    ``feature_rows`` is the opener: unlike every other Appearance line this one
    sits on no section, because it is offered on every trait row and every
    marking the player has. ``offers._opener_satisfied`` reads exactly that.
    """
    from world.character_creation.models import DistinctionOffer  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    authored_or_sample(
        DistinctionOffer,
        {
            "arrives_as": OfferArrival.CHOICE,
            "name": distinction.name,
            "player_line": distinction.description,
            "sort_order": sort_order,
            "is_active": True,
        },
        distinction=distinction,
        chapter=OfferChapter.APPEARANCE,
        feature_rows=True,
    )


def _ensure_opener(category) -> None:
    """Seed "Make It Distinctive" — the pick every other feature row hangs off."""
    from world.distinctions.models import Distinction  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    distinction = authored_or_sample(
        Distinction,
        {
            "name": "Make It Distinctive",
            "category": category,
            "description": (
                "PLACEHOLDER: one feature of yours is worth describing, and you get to "
                "describe it in your own words, in whatever colour it happens to be."
            ),
            "cost_per_rank": _OPENER_COST,
            "max_rank": 1,
            "taken_per_feature": True,
            "opens_feature": True,
        },
        slug=_OPENER_SLUG,
    )
    if distinction is not None:
        _ensure_offer(distinction, sort_order=0)


def _ensure_axis(category, axis: tuple[str, str, str, str], order: int) -> None:
    """Seed one presence axis and point its effect at the accent target it shares."""
    slug, name, target_name, line = axis
    from world.distinctions.models import Distinction, DistinctionEffect  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    distinction = authored_or_sample(
        Distinction,
        {
            "name": name,
            "category": category,
            "description": line,
            "cost_per_rank": _AXIS_COST_PER_TIER,
            "max_rank": _AXIS_MAX_RANK,
            "cg_max_rank": _AXIS_CG_MAX_RANK,
            "taken_per_feature": True,
            "requires_feature_opened": True,
        },
        slug=slug,
    )
    if distinction is None:
        return
    _ensure_offer(distinction, sort_order=order)
    # The accent targets are content-repo-owned and seeded by other clusters; a
    # clone missing one gets the distinction without its effect rather than nothing.
    target = ModifierTarget.objects.filter(name=target_name).first()
    if target is None:
        return
    authored_or_sample(
        DistinctionEffect,
        {
            "value_per_rank": _AXIS_PER_TIER,
            "description": f"+{_AXIS_PER_TIER} {target_name} a tier, while the feature shows.",
        },
        distinction=distinction,
        target=target,
    )


def seed_distinctive_features() -> None:
    """Cluster entry — the four per-feature Appearance rows and their offers (#3739).

    Runs after ``social_relationships`` (the allure target), ``crafting_materials``
    (menace, regal) and ``governance`` (the Command check the regal axis binds to),
    so every effect this seeds finds its target on the first pass.
    """
    category = _feature_category()
    if category is None:
        return
    _ensure_opener(category)
    for order, axis in enumerate(_AXES, start=1):
        _ensure_axis(category, axis, order)
