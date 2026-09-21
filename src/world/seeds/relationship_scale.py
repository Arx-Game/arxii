"""Seed the tie catalogue, tier ladder, growth config, and reaction-emoji catalog (#3957).

Every tie shares one ``RelationshipTier`` ladder (four rungs ratified on #1699:
25 / 100 / 500 / 2000 depth, unconditional — ``RelationshipTier`` is NOT a
content model) and one ``RelationshipGrowthConfig`` singleton. The web door
also gets a starter ``ReactionEmoji`` catalog (👍 stays cosmetic; one positive,
one negative — also unconditional).

All player-visible names/descriptions here are PLACEHOLDER prose for Apostate's
rewrite (tier names, type picker lines, emoji selection pending playtest).

``relationships.RelationshipType`` is staff-authored content (#3957, mirrors the
retired ``RelationshipTrack``'s #2698 discipline) — looked up rather than
invented unless ``SEED_SAMPLE_CONTENT`` is on, via ``authored_or_sample`` so a
re-seed never clobbers a staff edit. The eighteen-plus starter types below
(Heart/Company/Contest/Blood-and-oath/Teaching) seed in one pass keyed by
``name``, then a second pass wires each type's ``counterpart`` now that every
row exists (the self-FK can't be set at creation time when the counterpart
hasn't been created yet — e.g. Beloved needs Admirer's pk). ``loaddata``
cannot update idmapper rows (#946), so the tier ladder and growth config both
use ``update_or_create``/``get_or_create`` so an edited seed value still
re-applies on re-seed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.relationships.models import RelationshipType

# (tier_number, PLACEHOLDER name, depth_threshold, combat_bonus) — the one ladder every tie shares
_TIER_LADDER: list[tuple[int, str, int, int]] = [
    (1, "Noticed", 25, 1),
    (2, "Valued", 100, 2),
    (3, "Cherished", 500, 3),
    (4, "Inseparable", 2000, 4),
]

# (emoji, valence, sort_order) — PLACEHOLDER selection pending playtest (#1699).
_STARTER_EMOJI: list[tuple[str, int, int]] = [
    ("\U0001f44d", 0, 0),  # 👍 keeps today's cosmetic behavior
    ("❤️", 1, 1),  # ❤️ warms
    ("\U0001f620", -1, 2),  # 😠 cools
]

# (name, family, valence, fuels_escalation_spikes, PLACEHOLDER picker line). Grouped by family
# (matches RelationshipType.Meta.ordering); display_order is assigned sequentially per group
# below so the picker reads in this authored order, not alphabetically.
#
# fuels_escalation_spikes=True on Friend, Lover, Spouse, Kin, Rival, Enemy, Nemesis only
# (#872/#2013) — the surge engine's grief/peril/hated-foe legs read this flag.
_HEART_TYPES = (
    ("Lover", True, "Together, and not hiding it from yourself."),
    ("Beloved", False, "Loved from a distance."),
    ("Admirer", False, "Loving from a distance."),
    ("Betrothed", False, "Promised."),
    ("Spouse", True, "Married."),
)
_COMPANY_TYPES = (
    ("Friend", True, "Chosen company."),
    ("Confidant", False, "The one you tell."),
    ("Comrade", False, "Stood beside in danger."),
    ("Ally", False, "Common cause, for now."),
)
_CONTEST_TYPES = (
    ("Rival", True, "Measured against."),
    ("Enemy", True, "Open hostility."),
    ("Nemesis", True, "The one you would end."),
    ("Grudge", False, "A wrong not forgiven."),
)
_BLOOD_AND_OATH_TYPES = (
    ("Kin", True, "Family, by blood or by taking."),
    ("Ward", False, "In their keeping."),
    ("Guardian", False, "Theirs to keep."),
    ("Sworn", False, "An oath between you."),
    ("Liege", False, "Owed service."),
    ("Vassal", False, "Owing service."),
)
_TEACHING_TYPES = (
    ("Mentor", False, "Teaches you."),
    ("Student", False, "Taught by you."),
    ("Patron", False, "Sponsors you."),
    ("Protege", False, "Sponsored by you."),
)

# (type name -> counterpart type name); every other type is symmetric (counterpart=None,
# i.e. Friend pairs with Friend — see RelationshipType.counterpart_or_self).
_COUNTERPARTS: dict[str, str] = {
    "Beloved": "Admirer",
    "Admirer": "Beloved",
    "Ward": "Guardian",
    "Guardian": "Ward",
    "Liege": "Vassal",
    "Vassal": "Liege",
    "Mentor": "Student",
    "Student": "Mentor",
    "Patron": "Protege",
    "Protege": "Patron",
}


def ensure_relationship_tier_ladder() -> None:
    """Upsert the four rungs of the single tier ladder every tie shares (names PLACEHOLDER)."""
    from world.relationships.models import RelationshipTier  # noqa: PLC0415

    for tier_number, name, depth_threshold, combat_bonus in _TIER_LADDER:
        RelationshipTier.objects.update_or_create(
            tier_number=tier_number,
            defaults={
                "name": name,
                "depth_threshold": depth_threshold,
                "combat_bonus": combat_bonus,
            },
        )


def ensure_growth_config() -> None:
    """Ensure the ``RelationshipGrowthConfig`` singleton exists (field defaults are the config)."""
    from world.relationships.models import RelationshipGrowthConfig  # noqa: PLC0415

    RelationshipGrowthConfig.objects.get_or_create(pk=1)


def ensure_reaction_emoji() -> None:
    """Upsert the starter reaction-emoji catalog (selection PLACEHOLDER)."""
    from world.scenes.models import ReactionEmoji  # noqa: PLC0415

    for emoji, valence, sort_order in _STARTER_EMOJI:
        ReactionEmoji.objects.update_or_create(
            emoji=emoji,
            defaults={"valence": valence, "is_active": True, "sort_order": sort_order},
        )


def ensure_relationship_type_catalogue() -> dict[str, RelationshipType]:
    """Look up (or, under SEED_SAMPLE_CONTENT, invent) the starter tie-type catalogue.

    ``relationships.RelationshipType`` is content-repo-owned (#3957) — each type is
    looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on; a type
    missing from both the content repo and this dict (when sampling is off) is
    simply absent from the returned mapping, and ``_apply_counterparts`` skips
    any counterpart pair it doesn't find both halves of.
    """
    from world.relationships.constants import TypeFamily, TypeValence  # noqa: PLC0415
    from world.relationships.models import RelationshipType  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    groups = (
        (_HEART_TYPES, TypeFamily.HEART, TypeValence.WARM),
        (_COMPANY_TYPES, TypeFamily.COMPANY, TypeValence.WARM),
        (_CONTEST_TYPES, TypeFamily.CONTEST, TypeValence.HOSTILE),
        (_BLOOD_AND_OATH_TYPES, TypeFamily.BLOOD_AND_OATH, TypeValence.NEUTRAL),
        (_TEACHING_TYPES, TypeFamily.TEACHING, TypeValence.NEUTRAL),
    )
    # Kin is Blood-and-oath's one WARM exception to its group's NEUTRAL default.
    valence_overrides = {"Kin": TypeValence.WARM}

    types: dict[str, RelationshipType] = {}
    for rows, family, default_valence in groups:
        for position, (name, fuels_spikes, line) in enumerate(rows, start=1):
            defaults = {
                "slug": name.lower(),
                "description": line,
                "family": family,
                "valence": valence_overrides.get(name, default_valence),
                "display_order": position * 10,
                "fuels_escalation_spikes": fuels_spikes,
            }
            row = authored_or_sample(RelationshipType, defaults, name=name)
            if row is not None:
                types[name] = row

    _apply_counterparts(types)
    return types


def _apply_counterparts(types: dict[str, RelationshipType]) -> None:
    """Second pass: wire each type's ``counterpart`` now that every row exists (#3957).

    Only writes when the counterpart actually changes (avoids spurious UPDATE
    statements, mirroring ``consent.py``'s ``_apply_category_parents``).
    """
    for name, counterpart_name in _COUNTERPARTS.items():
        row = types.get(name)
        counterpart = types.get(counterpart_name)
        if row is None or counterpart is None:
            continue
        if row.counterpart_id != counterpart.pk:
            row.counterpart = counterpart
            row.save(update_fields=["counterpart"])


def seed_relationship_scale_content() -> None:
    """Cluster entry — tie-type catalogue, tier ladder, growth config, reaction emoji."""
    ensure_relationship_type_catalogue()
    ensure_relationship_tier_ladder()
    ensure_growth_config()
    ensure_reaction_emoji()
