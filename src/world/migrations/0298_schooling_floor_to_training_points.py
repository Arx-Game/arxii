"""Carry each schooling stance's Magic skill floor into training points (data only).

Slice 2 of #4659. ``SchoolingLine.magic_skill_floor`` was one level every active
Magic skill started at; a character now spends a pool of Magic-skill training points
instead, read from distinction effects on the ``magic_training_points`` target in the
``character_creation`` modifier category. 0299 drops the column.

Data disposition (ADR-0237): restructure. For each line with a floor above 0 and a
``grants`` distinction, the distinction's effect on that target is set so its value
at the line's rank equals ``floor * active Magic skill count``: the same total the
old floor gave a character, now spent instead of fixed. The value is written into
``scaling_values`` at index ``rank - 1``, keeping every other rank's value (ranks 1
and 2 grant the same distinction). The category and target rows are only looked up
or created when there is a floor to carry. A line with a floor but no ``grants``
carries nothing, since the stance granted nothing a draft could hold.

Reverse is a no-op: 0299's reverse restores the column at its default.
"""

from django.db import migrations

CG_MODIFIER_CATEGORY = "character_creation"
MAGIC_TRAINING_POINTS_TARGET = "magic_training_points"
MAGIC_TRAIT_CATEGORY = "magic"


def _value_at_rank(effect, rank):
    """The historical model has no methods; mirrors ``DistinctionEffect.get_value_at_rank``."""
    values = effect.scaling_values or []
    if len(values) >= rank:
        return values[rank - 1]
    if effect.value_per_rank is not None:
        return effect.value_per_rank * rank
    return 0


def carry_floors(apps, schema_editor):
    SchoolingLine = apps.get_model("arxii", "SchoolingLine")
    lines = list(
        SchoolingLine.objects.filter(magic_skill_floor__gt=0, grants__isnull=False).order_by("rank")
    )
    if not lines:
        return
    Skill = apps.get_model("arxii", "Skill")
    ModifierCategory = apps.get_model("arxii", "ModifierCategory")
    ModifierTarget = apps.get_model("arxii", "ModifierTarget")
    DistinctionEffect = apps.get_model("arxii", "DistinctionEffect")

    # Mirrors magic_category_skills(): MAGIC_SKILL_CHOICES plus the active flag.
    skill_count = Skill.objects.filter(trait__category=MAGIC_TRAIT_CATEGORY, is_active=True).count()
    category, _ = ModifierCategory.objects.get_or_create(name=CG_MODIFIER_CATEGORY)
    target, _ = ModifierTarget.objects.get_or_create(
        name=MAGIC_TRAINING_POINTS_TARGET,
        category=category,
        defaults={"description": "Points a draft spends on Magic skills at character creation."},
    )
    for line in lines:
        effect, _ = DistinctionEffect.objects.get_or_create(
            distinction_id=line.grants_id, target=target
        )
        rank = line.rank
        length = max(rank, len(effect.scaling_values or []))
        values = [_value_at_rank(effect, r) for r in range(1, length + 1)]
        values[rank - 1] = line.magic_skill_floor * skill_count
        effect.scaling_values = values
        effect.save(update_fields=["scaling_values"])


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0297_affinity_aura_type_backfill"),
    ]

    operations = [
        migrations.RunPython(carry_floors, migrations.RunPython.noop),
    ]
