"""House Stature catalogs (#3091) — PLACEHOLDER content.

Seeds the qualitative band vocabulary (headline prose is PLACEHOLDER for
Apostate's pass), the rank-relative prestige benefit bands (declining scale
across the top 100, minimal 101-1000, penalties for negative standing), and
the realm-cultural consort/paramour union kinds. Luxen recognizes no
consorts — expressed as the absence of a Luxen consort row, never a flag.
"""

from __future__ import annotations

# name, rank, min_percentile, threat_multiplier, headline_template
_BANDS = [
    ("Unassailable", 1, 92, "0.50", "PLACEHOLDER None dare test {org}."),
    ("Formidable", 2, 75, "0.75", "PLACEHOLDER Few would move against {org}."),
    ("Secure", 3, 55, "0.90", "PLACEHOLDER {org} stands firm."),
    ("Steady", 4, 40, "1.00", "PLACEHOLDER {org} holds its own."),
    ("Uncertain", 5, 22, "1.25", "PLACEHOLDER Eyes linger on {org}'s walls."),
    ("Vulnerable", 6, 8, "1.60", "PLACEHOLDER Wolves circle {org}."),
    ("Imperiled", 7, 0, "2.00", "PLACEHOLDER {org} bleeds, and the realm knows it."),
]

# name, min_rank, max_rank, negative_only, prosperity_bonus
_RANK_BANDS = [
    ("The First Name", 1, 1, False, 5),
    ("Names That Open Doors", 2, 10, False, 3),
    ("Names Worth Knowing", 11, 100, False, 2),
    ("Known Names", 101, 1000, False, 1),
    ("Names Best Whispered", None, None, True, -3),
]

# realm name, union kind name, max_concurrent
_CONSORT_KINDS = [
    ("Inferna", "Consort of Inferna", 3),
    ("Umbros", "Consort of Umbros", 1),
    ("Ariwn", "Consort of Ariwn", 1),
    ("Aythirmok", "Consort of Aythirmok", 1),
]


def ensure_stature_catalog() -> int:
    """Seed bands, rank bands, and consort vocabulary. Idempotent."""
    from world.realms.models import Realm  # noqa: PLC0415
    from world.roster.models import UnionKind  # noqa: PLC0415
    from world.societies.houses.models import PrestigeRankBand, StatureBand  # noqa: PLC0415

    created = 0
    for name, rank, min_percentile, multiplier, headline in _BANDS:
        _, was_created = StatureBand.objects.update_or_create(
            name=name,
            defaults={
                "rank": rank,
                "min_percentile": min_percentile,
                "threat_multiplier": multiplier,
                "headline_template": headline,
            },
        )
        created += was_created
    for name, min_rank, max_rank, negative_only, bonus in _RANK_BANDS:
        _, was_created = PrestigeRankBand.objects.update_or_create(
            name=name,
            defaults={
                "scope": PrestigeRankBand.Scope.ORG,
                "min_rank": min_rank if min_rank is not None else 1,
                "max_rank": max_rank,
                "negative_only": negative_only,
                "prosperity_bonus": bonus,
            },
        )
        created += was_created
    for realm_name, kind_name, cap in _CONSORT_KINDS:
        realm = Realm.objects.filter(name__iexact=realm_name).first()
        if realm is None:
            continue
        _, was_created = UnionKind.objects.update_or_create(
            name=kind_name,
            defaults={
                "realm": realm,
                "confers_wedlock": False,
                "stature_share_pct": 50,
                "contributes_to_origin_house": False,
                "requires_landed_title": True,
                "max_concurrent": cap,
            },
        )
        created += was_created
    _, was_created = UnionKind.objects.update_or_create(
        name="Paramour",
        defaults={
            "realm": None,
            "confers_wedlock": False,
            "stature_share_pct": 0,
            "contributes_to_origin_house": False,
            "requires_landed_title": False,
            "max_concurrent": None,
        },
    )
    created += was_created
    return created
