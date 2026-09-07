"""Data step for #3675: pairings and bundles become offers; slate lines get a state.

The one place a tradition is identified by its display name: the Unbound row has
no field-based signal before ``state`` lands. Runtime code reads ``state``.
"""

from django.db import migrations

UNBOUND_TRADITION_NAME = "Unbound"


def forwards(apps, schema_editor):
    Suggestion = apps.get_model("arxii", "GlimpseTagDistinctionSuggestion")
    Offer = apps.get_model("arxii", "DistinctionOffer")
    Choice = apps.get_model("arxii", "OriginTemplateSlotChoice")
    Slate = apps.get_model("arxii", "BeginningTradition")
    Draft = apps.get_model("arxii", "CharacterDraft")
    for row in Suggestion.objects.select_related("distinction", "tag"):
        Offer.objects.get_or_create(
            distinction_id=row.distinction_id,
            chapter="glimpse",
            glimpse_tag_id=row.tag_id,
            defaults={
                "arrives_as": "choice",
                "name": row.distinction.name,
                "sort_order": row.sort_order,
            },
        )
    for choice in Choice.objects.filter(grants_distinction__isnull=False).select_related(
        "grants_distinction"
    ):
        Offer.objects.get_or_create(
            distinction_id=choice.grants_distinction_id,
            chapter="lineage",
            origin_choice_id=choice.id,
            defaults={"arrives_as": "bundled", "name": choice.grants_distinction.name},
        )
    Slate.objects.filter(tradition__name=UNBOUND_TRADITION_NAME).update(state="self_taught")
    Draft.objects.filter(current_stage=4).update(current_stage=5)


class Migration(migrations.Migration):
    dependencies = [("arxii", "0106_distinction_offers_expand")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
