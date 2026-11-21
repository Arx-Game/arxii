"""Carry the two flat worship amounts onto outcome award rows (#4349). Data-only.

ADR-0237 disposition: restructure. ``CeremonyConfig.devotion_officiant`` (the favor every
finished ceremony paid its officiant) and ``ChosenFavorConfig.anima_recovery_bonus`` (the extra
anima a Chosen recovered every anima ritual) are replaced by ``FavorOutcomeAward`` rows by
ritual or Rites result. A later migration drops the two columns.

* The officiant value becomes the OFFICIANT row for the Success tier, and the Chosen anima
  value becomes the CHOSEN_ANIMA row for the Success tier, on the ``DevotionConfig``
  singleton. They are the only rows written: the other tiers are staff authoring (a tier with
  no row pays 0).
* Each value is the row's own when the config row exists, else the column's default (10 and
  5): a database that never opened a ceremony or the Chosen admin still paid those amounts, so
  the Success row keeps what that database paid.
* Nothing is written when the database holds no ``Success`` check outcome (a bare database
  has no outcome tiers, so there is nothing to attach a row to and nothing to carry). A row
  already present for the pair is left alone, so a second run adds nothing.

# seed-data-ok: ADR-0237 restructure: carries the two retired config columns' live values (or
# their defaults) onto award rows; it authors nothing new.

It prints what it carried.
"""

import sys

from django.db import migrations

#: ``FavorAwardKind`` values, copied here because a migration is frozen.
OFFICIANT_KIND = "officiant"
CHOSEN_ANIMA_KIND = "chosen_anima"
SUCCESS_OUTCOME_NAME = "Success"
#: The retired columns' defaults, read when no config row exists.
DEFAULT_OFFICIANT_FAVOR = 10
DEFAULT_CHOSEN_ANIMA_BONUS = 5


def carry_amounts(apps, schema_editor):
    CheckOutcome = apps.get_model("arxii", "CheckOutcome")
    CeremonyConfig = apps.get_model("arxii", "CeremonyConfig")
    ChosenFavorConfig = apps.get_model("arxii", "ChosenFavorConfig")
    DevotionConfig = apps.get_model("arxii", "DevotionConfig")
    FavorOutcomeAward = apps.get_model("arxii", "FavorOutcomeAward")

    success = CheckOutcome.objects.filter(name=SUCCESS_OUTCOME_NAME).first()
    if success is None:
        print("  no Success check outcome: nothing to carry", file=sys.stderr)
        return
    ceremony = CeremonyConfig.objects.order_by("pk").first()
    chosen = ChosenFavorConfig.objects.order_by("pk").first()
    officiant = ceremony.devotion_officiant if ceremony is not None else DEFAULT_OFFICIANT_FAVOR
    anima = chosen.anima_recovery_bonus if chosen is not None else DEFAULT_CHOSEN_ANIMA_BONUS
    config, _ = DevotionConfig.objects.get_or_create(pk=1)
    for kind, amount in ((OFFICIANT_KIND, officiant), (CHOSEN_ANIMA_KIND, anima)):
        row, created = FavorOutcomeAward.objects.get_or_create(
            config=config, kind=kind, outcome_tier=success, defaults={"amount": amount}
        )
        print(
            f"  {kind} / Success: {'wrote' if created else 'kept'} {row.amount}",
            file=sys.stderr,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0468_worship_scaled_outcomes_schema"),
    ]

    operations = [
        migrations.RunPython(carry_amounts, migrations.RunPython.noop),
    ]
