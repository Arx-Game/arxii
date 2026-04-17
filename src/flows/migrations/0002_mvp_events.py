from django.db import migrations

MVP_EVENTS: list[tuple[str, str]] = [
    ("attack_pre_resolve", "Attack Pre-Resolve"),
    ("attack_landed", "Attack Landed"),
    ("attack_missed", "Attack Missed"),
    ("damage_pre_apply", "Damage Pre-Apply"),
    ("damage_applied", "Damage Applied"),
    ("character_incapacitated", "Character Incapacitated"),
    ("character_killed", "Character Killed"),
    ("move_pre_depart", "Move: Pre-Depart"),
    ("moved", "Moved"),
    ("examine_pre", "Examine Pre"),
    ("examined", "Examined"),
    ("condition_pre_apply", "Condition Pre-Apply"),
    ("condition_applied", "Condition Applied"),
    ("condition_stage_changed", "Condition Stage Changed"),
    ("condition_removed", "Condition Removed"),
    ("technique_pre_cast", "Technique Pre-Cast"),
    ("technique_cast", "Technique Cast"),
    ("technique_affected", "Technique Affected"),
]


def seed_events(apps, schema_editor):
    Event = apps.get_model("flows", "Event")
    for name, label in MVP_EVENTS:
        Event.objects.get_or_create(name=name, defaults={"label": label})


def unseed_events(apps, schema_editor):
    Event = apps.get_model("flows", "Event")
    Event.objects.filter(name__in=[n for n, _ in MVP_EVENTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("flows", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_events, unseed_events),
    ]
