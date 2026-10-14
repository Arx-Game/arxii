# Data only (#4333). Gives every existing WorshippedBeing its two favor modifier
# targets ("<being> favor invocation", "<being> favor earning") and creates the two
# favor categories and their single "any being" targets.
#
# New beings get theirs from ensure_being_modifier_targets, called explicitly by the
# Deity Editor's save_being; this migration covers the beings that already exist. The
# rows are derived mechanically from WorshippedBeing rows, one per being per category;
# nothing authored is invented. A frozen copy of the service's naming so a later
# rename there never changes what this migration writes on replay.

from django.db import migrations

TARGET_NAME_MAX_LENGTH = 100
FAVOR_INVOCATION = "favor_invocation"
FAVOR_EARNING = "favor_earning"
_CATEGORIES = (
    (
        FAVOR_INVOCATION,
        "favor invocation",
        "Difficulty points eased on the invocation check for a being (#4333).",
    ),
    (
        FAVOR_EARNING,
        "favor earning",
        "Percentage points added to the earning rate with a being (#4333).",
    ),
)


def backfill_being_favor_targets(apps, schema_editor):
    ModifierCategory = apps.get_model("arxii", "ModifierCategory")
    ModifierTarget = apps.get_model("arxii", "ModifierTarget")
    WorshippedBeing = apps.get_model("arxii", "WorshippedBeing")

    for category_name, label, description in _CATEGORIES:
        category, _ = ModifierCategory.objects.get_or_create(
            name=category_name, defaults={"description": description}
        )
        ModifierTarget.objects.get_or_create(
            category=category,
            name=f"Any being {label}",
            defaults={"target_being": None},
        )
        for being in WorshippedBeing.objects.all():
            ModifierTarget.objects.get_or_create(
                category=category,
                target_being=being,
                defaults={"name": _target_name(being.name, label)},
            )


def _target_name(being_name, label):
    suffix = f" {label}"
    return f"{being_name[: TARGET_NAME_MAX_LENGTH - len(suffix)]}{suffix}"


def remove_being_favor_targets(apps, schema_editor):
    """Reverse: drop the favor categories and their targets, so that migrating
    forward again (after 0222's reverse drops target_being) starts clean."""
    ModifierCategory = apps.get_model("arxii", "ModifierCategory")
    ModifierTarget = apps.get_model("arxii", "ModifierTarget")

    names = [name for name, _, _ in _CATEGORIES]
    ModifierTarget.objects.filter(category__name__in=names).delete()
    ModifierCategory.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0223_favor_invocation"),
    ]

    operations = [
        migrations.RunPython(backfill_being_favor_targets, remove_being_favor_targets),
    ]
