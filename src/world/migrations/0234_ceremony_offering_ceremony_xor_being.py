# The CHECK on CeremonyOffering in its own migration (#4333 slice 2): it ties the
# ``being`` column 0233 adds to ``ceremony``. Every existing row has a ceremony and
# no being (``ceremony`` was NOT NULL until 0233), so it satisfies the first arm.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0233_pledges_and_sacrifices"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="ceremonyoffering",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("being__isnull", True), ("ceremony__isnull", False)),
                    models.Q(("being__isnull", False), ("ceremony__isnull", True)),
                    _connector="OR",
                ),
                name="ceremony_offering_ceremony_xor_being",
            ),
        ),
    ]
