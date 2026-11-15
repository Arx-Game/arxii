"""Seed the three kindled strengths from FuryConfig and collapse drift offers (#5124).

Data only (the schema comes from 0411 and 0412; the FuryConfig fields it reads go in 0414).

Fury's depth cap, bonus and ease used to come from a bond tier through three FuryConfig
numbers. They now come from the strength a kindled resonance reaches, so this copies them
into the three KindledStrengthTier rows. Strength ``r`` reaches Fury depth ``r``: its
``min_bond_tier`` is ``r x provocation_cap_per_tier``, its ``give_in_max_depth`` is ``r``, its
bonus is ``r x bonus_scale_per_cap_point`` percent and its ease is
``r x cap_ease_per_point``. With no FuryConfig row the field defaults (1, 10, 1) stand in for its
numbers, as they did at runtime, so Fury stays reachable. Every other column is left 0 for staff to tune (a reach column of 0 means the
strength is not reached that way). A tier that already exists is left as it is.

It also keeps one open DriftConversionOffer per character, the newest, because 0414 makes the
offer unique per character. An offer is play state (the chance to atone, resettable); its caps
go with it. The deletion cannot be reversed.

Reversing deletes the three seeded rows.
"""

from django.db import migrations

# seed-data-ok: #5124 three prose-light mechanical tuning rows copied from the FuryConfig
# values they replace; names are placeholders staff rename.

TIER_NAMES = {1: "Faint", 2: "Strong", 3: "Blazing"}


def seed_tiers(apps, schema_editor):
    FuryConfig = apps.get_model("arxii", "FuryConfig")
    KindledStrengthTier = apps.get_model("arxii", "KindledStrengthTier")
    config = FuryConfig.objects.filter(pk=1).first() or FuryConfig.objects.first()
    # With no FuryConfig row Fury ran on the field defaults (1, 10, 1), so the tiers are made
    # from those and Fury stays reachable.
    per_tier = config.provocation_cap_per_tier if config is not None else 1
    bonus_scale = config.bonus_scale_per_cap_point if config is not None else 10
    ease = config.cap_ease_per_point if config is not None else 1
    for rank, name in TIER_NAMES.items():
        values = {
            "name": name,
            "min_bond_tier": rank * per_tier,
            "give_in_max_depth": rank,
            "give_in_bonus_percent": rank * bonus_scale,
            "give_in_ease": rank * ease,
        }
        KindledStrengthTier.objects.get_or_create(rank=rank, defaults=values)


def unseed_tiers(apps, schema_editor):
    KindledStrengthTier = apps.get_model("arxii", "KindledStrengthTier")
    KindledStrengthTier.objects.filter(rank__in=TIER_NAMES, name__in=TIER_NAMES.values()).delete()


def collapse_offers(apps, schema_editor):
    DriftConversionOffer = apps.get_model("arxii", "DriftConversionOffer")
    seen: set[int] = set()
    stale: list[int] = []
    rows = DriftConversionOffer.objects.order_by("-created_at", "-id").values_list(
        "id", "character_sheet_id"
    )
    for offer_id, sheet_id in rows:
        if sheet_id in seen:
            stale.append(offer_id)
        seen.add(sheet_id)
    if stale:
        DriftConversionOffer.objects.filter(pk__in=stale).delete()


class Migration(migrations.Migration):
    dependencies = [("arxii", "0412_resonance_grant_kindled_shapes")]

    operations = [
        migrations.RunPython(seed_tiers, unseed_tiers),
        migrations.RunPython(collapse_offers, migrations.RunPython.noop),
    ]
