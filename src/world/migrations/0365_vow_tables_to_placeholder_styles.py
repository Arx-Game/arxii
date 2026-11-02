"""Carry the vow defense profile and gear compatibility rows onto placeholder styles (#4975).

Data only (0366 drops the two tables). ADR-0237 restructure: each role's
``CovenantRoleDefenseProfile`` (defense style, armor share) and
``GearArchetypeCompatibility`` rows (gear kinds) move onto ``CombatStyle`` rows that list
the role in ``compatible_roles``, so no authored row is lost before the tables go.

One placeholder style per distinct (defense style, armor share, weapon/armor kinds). Its
name is a plain "Placeholder <Defense> Style <n>", the description is blank, and skill,
hit stat and Traditions stay empty, so Required content flags it until staff author it
(owner ruling 2026-11-02: no character holds a vow, so nothing in play depends on these
rows). A role with gear rows and no profile gets Mitigation at a full share, the behavior
it had with no profile. Gear kinds a style cannot hold (jewelry, clothing, other) have no
``CombatStyleGear`` row to land on; the count of those skipped is printed.

Everything is copied here, never imported from app code, so the migration cannot drift.
Idempotent: a style is found by its name. Reversing is a no-op: the styles are plain
content rows and the old tables are restored empty by reversing 0366.
"""

from collections.abc import Iterable

from django.db import migrations

# world.covenants.constants.DefenseStyle labels as of #4975.
DEFENSE_LABELS = {"gear_soak": "Mitigation", "evasion": "Evasion", "barrier": "Barrier"}
# What a role with gear rows and no profile had: no vow defense style, all gear additive.
NO_PROFILE_STYLE = "gear_soak"
FULL_SHARE_TENTHS = 10

# world.items.constants.WEAPON_ARCHETYPES | ARMOR_ARCHETYPES as of #4975: the only kinds a
# CombatStyleGear row can hold.
STYLE_GEAR_KINDS = frozenset(
    {
        "melee_one_hand",
        "melee_two_hand",
        "ranged",
        "thrown",
        "shield",
        "lance",
        "unarmed",
        "light_armor",
        "medium_armor",
        "heavy_armor",
        "robe",
    }
)

StyleKey = tuple[str, int, tuple[str, ...]]


def group_roles(
    profiles: dict[int, tuple[str, int]],
    gear: dict[int, set[str]],
) -> tuple[dict[StyleKey, list[int]], int]:
    """Group role ids by (defense style, armor share, style-holdable gear kinds).

    ``profiles`` maps a role id to its (defense style, gear_additive_tenths); ``gear`` maps
    a role id to the archetype values it was compatible with. Returns the groups and the
    number of gear kinds skipped because a style cannot hold them.
    """
    groups: dict[StyleKey, list[int]] = {}
    skipped = 0
    for role_id in sorted(set(profiles) | set(gear)):
        style, tenths = profiles.get(role_id, (NO_PROFILE_STYLE, FULL_SHARE_TENTHS))
        kinds = gear.get(role_id, set())
        skipped += len(kinds - STYLE_GEAR_KINDS)
        key = (style, min(tenths, FULL_SHARE_TENTHS), tuple(sorted(kinds & STYLE_GEAR_KINDS)))
        groups.setdefault(key, []).append(role_id)
    return groups, skipped


def style_names(keys: Iterable[StyleKey]) -> dict[StyleKey, str]:
    """Name each key "Placeholder <Defense> Style <n>", n counting per label from 1."""
    counters: dict[str, int] = {}
    names: dict[StyleKey, str] = {}
    for key in sorted(keys):
        label = DEFENSE_LABELS.get(key[0], key[0])
        counters[label] = counters.get(label, 0) + 1
        names[key] = f"Placeholder {label} Style {counters[label]}"
    return names


def carry_vow_tables_to_styles(apps, schema_editor) -> None:
    Profile = apps.get_model("arxii", "CovenantRoleDefenseProfile")
    Compat = apps.get_model("arxii", "GearArchetypeCompatibility")
    CombatStyle = apps.get_model("arxii", "CombatStyle")
    CombatStyleGear = apps.get_model("arxii", "CombatStyleGear")

    profiles = {
        role_id: (style, tenths)
        for role_id, style, tenths in Profile.objects.values_list(
            "covenant_role_id", "style", "gear_additive_tenths"
        )
    }
    gear: dict[int, set[str]] = {}
    for role_id, archetype in Compat.objects.values_list("covenant_role_id", "gear_archetype"):
        gear.setdefault(role_id, set()).add(archetype)

    groups, skipped = group_roles(profiles, gear)
    names = style_names(groups)
    for key, role_ids in groups.items():
        defense_style, share, kinds = key
        style, _ = CombatStyle.objects.get_or_create(
            name=names[key],
            defaults={
                "description": "",
                "defense_style": defense_style,
                "armor_share_tenths": share,
            },
        )
        for kind in kinds:
            CombatStyleGear.objects.get_or_create(style=style, gear_archetype=kind)
        style.compatible_roles.add(*role_ids)
    # The PR names the discarded gear kinds from this line.
    print(
        f"\n  0365: {len(groups)} placeholder styles from {len(profiles)} profiles and "
        f"{sum(len(k) for k in gear.values())} gear rows; "
        f"{skipped} gear kinds skipped (not weapon/armor)"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0364_vow_pick_respec_ap_cost"),
    ]

    operations = [
        migrations.RunPython(carry_vow_tables_to_styles, migrations.RunPython.noop),
    ]
