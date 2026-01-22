# Generated manually for initial personality distinctions (Abyssal and Celestial)

from django.db import migrations


def create_personality_distinctions(apps, schema_editor):
    """Create the initial Abyssal and Celestial personality distinctions."""
    DistinctionCategory = apps.get_model("distinctions", "DistinctionCategory")
    Distinction = apps.get_model("distinctions", "Distinction")
    DistinctionEffect = apps.get_model("distinctions", "DistinctionEffect")
    DistinctionTag = apps.get_model("distinctions", "DistinctionTag")

    # Get or create the Personality category
    personality_category, _ = DistinctionCategory.objects.get_or_create(
        slug="personality",
        defaults={
            "name": "Personality",
            "description": (
                "Distinctions related to temperament, behavior patterns, and personal "
                "traits. Includes advantages and disadvantages affecting social "
                "interactions, emotional responses, and character tendencies."
            ),
            "display_order": 3,
        },
    )

    # Create tags
    abyssal_tag, _ = DistinctionTag.objects.get_or_create(
        slug="abyssal",
        defaults={"name": "Abyssal"},
    )
    celestial_tag, _ = DistinctionTag.objects.get_or_create(
        slug="celestial",
        defaults={"name": "Celestial"},
    )
    virtue_tag, _ = DistinctionTag.objects.get_or_create(
        slug="virtue",
        defaults={"name": "Virtue"},
    )
    sin_tag, _ = DistinctionTag.objects.get_or_create(
        slug="sin",
        defaults={"name": "Sin"},
    )
    goals_tag, _ = DistinctionTag.objects.get_or_create(
        slug="goals",
        defaults={"name": "Goals"},
    )

    # =========================================================================
    # ABYSSAL DISTINCTIONS
    # =========================================================================

    # Rapacious (Positive, 5 pts/rank, max 3)
    rapacious, created = Distinction.objects.get_or_create(
        slug="rapacious",
        defaults={
            "name": "Rapacious",
            "description": (
                "A rapacious character has a hunger and drive for what they want "
                "that can be unsettling even to their allies. Ruthless and even "
                "predatory, there is a hint of the abyss around their wants."
            ),
            "category": personality_category,
            "cost_per_rank": 5,
            "max_rank": 3,
            "is_active": True,
        },
    )
    if created:
        rapacious.tags.add(abyssal_tag, sin_tag, goals_tag)
        # Effect: Abyssal affinity (starting)
        DistinctionEffect.objects.create(
            distinction=rapacious,
            effect_type="affinity_modifier",
            target="abyssal",
            value_per_rank=5,
            description="+5 Abyssal affinity per rank.",
        )
        # Effect: +10 per rank on goal-related checks
        DistinctionEffect.objects.create(
            distinction=rapacious,
            effect_type="goal_modifier",
            target="all",  # All goal domains
            value_per_rank=10,
            description="+10 per rank on checks involving tagged goals.",
        )

    # Voracious (Positive, 5 pts/rank, max 3)
    voracious, created = Distinction.objects.get_or_create(
        slug="voracious",
        defaults={
            "name": "Voracious",
            "description": (
                "A voracious character is driven by need in a way that borders on "
                "compulsion. When the hunger calls, little else matters."
            ),
            "category": personality_category,
            "cost_per_rank": 5,
            "max_rank": 3,
            "is_active": True,
        },
    )
    if created:
        voracious.tags.add(abyssal_tag, sin_tag, goals_tag)
        # Effect: Abyssal affinity (starting)
        DistinctionEffect.objects.create(
            distinction=voracious,
            effect_type="affinity_modifier",
            target="abyssal",
            value_per_rank=5,
            description="+5 Abyssal affinity per rank.",
        )
        # Effect: +20 per rank on Needs domain checks
        DistinctionEffect.objects.create(
            distinction=voracious,
            effect_type="goal_modifier",
            target="needs",  # Only Needs domain
            value_per_rank=20,
            description="+20 per rank on checks involving Needs goals.",
        )

    # Wrathful (Negative, -5 pts)
    wrathful, created = Distinction.objects.get_or_create(
        slug="wrathful",
        defaults={
            "name": "Wrathful",
            "description": (
                "Rage simmers beneath the surface, and when provoked, it erupts "
                "with terrible force. A wrathful character struggles to contain "
                "their fury but channels devastating intensity when unleashed."
            ),
            "category": personality_category,
            "cost_per_rank": -5,
            "max_rank": 1,
            "is_active": True,
        },
    )
    if created:
        wrathful.tags.add(abyssal_tag, sin_tag)
        # Effect: Abyssal affinity (moderate)
        DistinctionEffect.objects.create(
            distinction=wrathful,
            effect_type="affinity_modifier",
            target="abyssal",
            value_per_rank=10,
            description="+10 Abyssal affinity.",
        )
        # Effect: -1 starting Willpower
        DistinctionEffect.objects.create(
            distinction=wrathful,
            effect_type="stat_modifier",
            target="willpower",
            value_per_rank=-1,
            description="-1 starting Willpower.",
        )
        # Effect: -10 control when angry
        DistinctionEffect.objects.create(
            distinction=wrathful,
            effect_type="roll_modifier",
            target="control",
            value_per_rank=-10,
            description="-10 control when angry.",
        )
        # Effect: +10 intensity when angry
        DistinctionEffect.objects.create(
            distinction=wrathful,
            effect_type="roll_modifier",
            target="intensity",
            value_per_rank=10,
            description="+10 intensity when angry.",
        )

    # Hubris (Negative, -5 pts)
    hubris, created = Distinction.objects.get_or_create(
        slug="hubris",
        defaults={
            "name": "Hubris",
            "description": (
                "Pride goeth before the fall, and a character with hubris has pride "
                "in abundance. They cannot bear embarrassment or humiliation, "
                "sometimes to their great detriment."
            ),
            "category": personality_category,
            "cost_per_rank": -5,
            "max_rank": 1,
            "is_active": True,
        },
    )
    if created:
        hubris.tags.add(abyssal_tag, sin_tag)
        # Effect: Abyssal affinity (significant)
        DistinctionEffect.objects.create(
            distinction=hubris,
            effect_type="affinity_modifier",
            target="abyssal",
            value_per_rank=15,
            description="+15 Abyssal affinity.",
        )
        # Effect: -20 when pride is injured
        DistinctionEffect.objects.create(
            distinction=hubris,
            effect_type="roll_modifier",
            target="pride_injured",
            value_per_rank=-20,
            description="-20 to any check where pride is injured.",
        )
        # Effect: Code-handled for removing graceful exit options
        DistinctionEffect.objects.create(
            distinction=hubris,
            effect_type="code_handled",
            target="hubris_no_graceful_exit",
            description="Removes graceful exit options that would cause embarrassment.",
        )

    # =========================================================================
    # CELESTIAL DISTINCTIONS
    # =========================================================================

    # Patient (Positive, 10 pts)
    patient, created = Distinction.objects.get_or_create(
        slug="patient",
        defaults={
            "name": "Patient",
            "description": (
                "A patient character endures what others cannot. They wait, they "
                "persist, and they maintain control when others would break."
            ),
            "category": personality_category,
            "cost_per_rank": 10,
            "max_rank": 1,
            "is_active": True,
        },
    )
    if created:
        patient.tags.add(celestial_tag, virtue_tag)
        # Effect: Celestial affinity (small)
        DistinctionEffect.objects.create(
            distinction=patient,
            effect_type="affinity_modifier",
            target="celestial",
            value_per_rank=5,
            description="+5 Celestial affinity.",
        )
        # Effect: +1 starting Willpower
        DistinctionEffect.objects.create(
            distinction=patient,
            effect_type="stat_modifier",
            target="willpower",
            value_per_rank=1,
            description="+1 starting Willpower.",
        )
        # Effect: +10 control
        DistinctionEffect.objects.create(
            distinction=patient,
            effect_type="roll_modifier",
            target="control",
            value_per_rank=10,
            description="+10 control.",
        )


def reverse_personality_distinctions(apps, schema_editor):
    """Remove the personality distinctions."""
    Distinction = apps.get_model("distinctions", "Distinction")
    DistinctionTag = apps.get_model("distinctions", "DistinctionTag")

    # Remove distinctions
    slugs = ["rapacious", "voracious", "wrathful", "hubris", "patient"]
    Distinction.objects.filter(slug__in=slugs).delete()

    # Remove tags (only if not used by other distinctions)
    tag_slugs = ["abyssal", "celestial", "virtue", "sin", "goals"]
    for slug in tag_slugs:
        tag = DistinctionTag.objects.filter(slug=slug).first()
        if tag and not tag.distinctions.exists():
            tag.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("distinctions", "0003_refactor_simplify_models"),
    ]

    operations = [
        migrations.RunPython(create_personality_distinctions, reverse_personality_distinctions),
    ]
