# Data-only (#4378). Production's Failure, Partial Success and Success outcome rows were
# created by a test factory called from seed code, with a random success_level and Faker
# sentences in description and display_template: Success read -4 and Failure read 3, so
# every roll was read backwards. This restores the seeded levels, keyed by name (never by
# pk), and blanks the Faker text, which no one authored and the seed leaves blank.
#
# ADR-0237 disposition: restructure. Wrong success_level values are corrected in place;
# no authored text is lost, because the only text touched is the sentence-shaped Faker
# filler on the three rows, matched by shape and not removed from any other row.

import re

from django.db import migrations

# name -> success_level, as world.seeds.checks seeds them (CANONICAL_OUTCOME_LEVELS).
# Copied, not imported: a migration must not follow later changes to app code.
CANONICAL_LEVELS = {
    "Critical Failure": -2,
    "Failure": -1,
    "Partial Success": 0,
    "Success": 1,
    "Critical Success": 2,
}

# Faker's ``sentence``: a capitalised run of lowercase words ending in a full stop.
FAKER_SENTENCE = re.compile(r"^[A-Z][a-z]+( [a-z]+)*\.$")


def restore_levels(apps, schema_editor):
    CheckOutcome = apps.get_model("arxii", "CheckOutcome")
    for name, level in CANONICAL_LEVELS.items():
        row = CheckOutcome.objects.filter(name=name).first()
        if row is None:
            continue
        changed = []
        if row.success_level != level:
            row.success_level = level
            changed.append("success_level")
        for field in ("description", "display_template"):
            if FAKER_SENTENCE.match(getattr(row, field)):
                setattr(row, field, "")
                changed.append(field)
        if changed:
            row.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0234_ceremony_offering_ceremony_xor_being"),
    ]

    operations = [
        migrations.RunPython(restore_levels, migrations.RunPython.noop),
    ]
