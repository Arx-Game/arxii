"""Carry each anima ritual's single resonance onto its two picks (#5280). Data-only.

ADR-0237 disposition: restructure. ``RitualCheckConfig.resonance`` (the one resonance an anima
ritual earned) is replaced by ``primal_resonance`` and ``outward_resonance``. A later migration
drops the old column.

* A row whose resonance is of the Primal affinity writes it to ``primal_resonance``; any other
  affinity writes it to ``outward_resonance``.
* A row whose target pick is already set is left alone, so a second run adds nothing and never
  overwrites a pick a player has since made.
* Production held no value in ``resonance`` on any of its five rows in the last dump (taken
  2026-11-15), so this carried nothing there at the time of writing. It is written anyway so a
  database that gained a value before the deploy loses none.
* Reverse: ``primal_resonance`` (else ``outward_resonance``) is copied back into ``resonance``
  where that column is empty.

It prints how many rows it carried.

# seed-data-ok: ADR-0237 restructure: moves an existing column's live values onto its
# replacement columns; it authors nothing new.
"""

import sys

from django.db import migrations

#: ``AFFINITY_PRIMAL``, copied here because a migration is frozen.
PRIMAL_AFFINITY_NAME = "Primal"


def carry_forward(apps, schema_editor):
    RitualCheckConfig = apps.get_model("arxii", "RitualCheckConfig")
    carried = 0
    rows = (
        RitualCheckConfig.objects.filter(resonance__isnull=False)
        .select_related("resonance__affinity")
        .iterator()
    )
    for config in rows:
        if config.resonance.affinity.name == PRIMAL_AFFINITY_NAME:
            if config.primal_resonance_id is not None:
                continue
            config.primal_resonance_id = config.resonance_id
            config.save(update_fields=["primal_resonance"])
        else:
            if config.outward_resonance_id is not None:
                continue
            config.outward_resonance_id = config.resonance_id
            config.save(update_fields=["outward_resonance"])
        carried += 1
    print(f"  anima ritual picks: carried {carried} resonance(s)", file=sys.stderr)


def carry_back(apps, schema_editor):
    RitualCheckConfig = apps.get_model("arxii", "RitualCheckConfig")
    for config in RitualCheckConfig.objects.filter(resonance__isnull=True).iterator():
        pick_id = config.primal_resonance_id or config.outward_resonance_id
        if pick_id is None:
            continue
        config.resonance_id = pick_id
        config.save(update_fields=["resonance"])


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0475_anima_ritual_two_picks_expand"),
    ]

    operations = [
        migrations.RunPython(carry_forward, carry_back),
    ]
