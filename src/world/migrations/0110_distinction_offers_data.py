"""Data step for #3675: pairings and bundles become offers; slate lines get a state.

Two lines in ``forwards()`` are the only place a tradition row is identified by
name or by its old drawback's tag, rather than by ``state``: the Unbound row (by
tradition name) and any row whose ``required_distinction`` carries the
``orphaned-tradition-marker`` tag (the pre-#3675 orphaned-tradition signal). Both
are migration-only, never repeated in runtime code, which reads ``state``. A
production dump checked on 2026-09-06 showed all 40 slate rows with
``required_distinction`` null, so both lines are expected no-ops in production
today; they exist so a database that does hold rows in this shape (a staff
edit, a fixture, a differently-seeded environment) still migrates correctly.
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
    Slate.objects.filter(required_distinction__tags__slug="orphaned-tradition-marker").update(
        state="teachers_gone"
    )
    Slate.objects.filter(tradition__name=UNBOUND_TRADITION_NAME).update(state="self_taught")
    Draft.objects.filter(current_stage=4).update(current_stage=5)


class Migration(migrations.Migration):
    dependencies = [("arxii", "0109_distinction_offers_expand")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
