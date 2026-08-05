# One axis, no skin special-case (#2985): a cut exposes whatever lies beneath
# it — stockings, or skin when nothing is underneath. Hand-written because
# 0109 merged under the old name mid-design (Apostate's refinement,
# 2026-08-05); the AlterField carries the rewritten help_text alongside the
# rename.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0113_partition_interaction"),
    ]

    operations = [
        migrations.RenameField(
            model_name="silhouette",
            old_name="exposes_skin",
            new_name="exposes_beneath",
        ),
        migrations.AlterField(
            model_name="silhouette",
            name="exposes_beneath",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Whether this cut exposes whatever lies beneath it (#2985): the slit "
                    "gown shows the stockings — or the skin and its markings when nothing "
                    "is underneath. ONE axis, no skin special-case: skin is just what you "
                    "find when you run out of layers (Apostate's ruling, 2026-08-05; "
                    "plain cuts conceal beneath by default). Revealing-ness is SHAPE, so "
                    "it lives on the silhouette — the crafter's cut pick at making "
                    "decides it per instance. Composes with ItemTemplate.is_revealing "
                    "(material sheerness) as an OR: either exposes the layer below."
                ),
            ),
        ),
    ]
