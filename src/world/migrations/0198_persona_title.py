"""Titles belong to the Persona, not the CharacterSheet (#3466).

Retargets ``CharacterTitle`` -> ``PersonaTitle`` and gives it a second branch: a title can
now come from an authored ``reward`` (unchanged) or from a ``legend_entry`` (a deed that
crossed its station's threshold). A masked deed's title lands on the mask's own persona,
never on the character sheet, which is what keeps an honor from ever outing anyone.

Sequenced as RenameModel -> AddField(persona, null=True) -> RunPython backfill ->
AlterField(persona, null=False) -> RemoveField(character_sheet) -> AlterField(reward,
null=True) -> AddField(legend_entry) -> AddConstraint(...) so the table is never left in
a half-migrated state between steps.
"""

from django.db import migrations, models
import django.db.models.deletion


def forwards(apps, schema_editor):
    """Carry every existing title onto its sheet's PRIMARY persona (#3466).

    Every pre-existing title was achievement-earned by the public identity, so the
    primary persona is the semantically correct home, not merely a convenient one.
    A sheet with no PRIMARY persona is a violated invariant and must fail loudly.
    """
    PersonaTitle = apps.get_model("arxii", "PersonaTitle")
    Persona = apps.get_model("arxii", "Persona")
    primaries = {
        p.character_sheet_id: p.pk
        # Literal "primary" (not PersonaType.PRIMARY) - migrations must not import
        # runtime code. PersonaType.PRIMARY == "primary" (world/scenes/constants.py:78).
        for p in Persona.objects.filter(persona_type="primary")
    }
    for title in PersonaTitle.objects.all().iterator():
        persona_id = primaries.get(title.character_sheet_id)
        if persona_id is None:
            message = (
                f"CharacterSheet {title.character_sheet_id} has no PRIMARY persona; "
                "cannot migrate its titles. Fix the data, do not skip the row."
            )
            raise RuntimeError(message)
        title.persona_id = persona_id
        title.save(update_fields=["persona_id"])


def backwards(apps, schema_editor):
    """Map each title's persona back onto its character_sheet (#3466).

    Every title migrated forwards came from a PRIMARY persona (this migration's own
    forwards guarantees it, and nothing else grants titles pre-#3466), so
    ``persona.character_sheet_id`` is exactly the value ``forwards`` read it from.

    THIS MIGRATION IS FORWARD-ONLY IN PRACTICE, and this function will never actually
    run to completion (whole-branch-review Minor). Reversing a migration replays its
    operations in reverse order, so the reverse of the later ``RemoveField(...,
    "character_sheet")`` operation below — an ``AddField`` re-adding that column as
    the NOT NULL FK it originally was, with no default — runs BEFORE this RunPython's
    reverse (this ``backwards`` function) ever gets a chance to backfill it. On any
    table already holding rows (which every populated deploy has), that AddField
    fails outright: Postgres refuses to add a NOT-NULL column with no default to a
    non-empty table. Keeping this function is still worth it for readability (it
    documents the intended data mapping precisely, and would work if invoked in
    isolation) — just never rely on ``migrate arxii 0195`` succeeding past this point.
    """
    PersonaTitle = apps.get_model("arxii", "PersonaTitle")
    Persona = apps.get_model("arxii", "Persona")
    sheet_by_persona = dict(Persona.objects.values_list("pk", "character_sheet_id"))
    for title in PersonaTitle.objects.all().iterator():
        title.character_sheet_id = sheet_by_persona.get(title.persona_id)
        title.save(update_fields=["character_sheet_id"])


class Migration(migrations.Migration):
    dependencies = [("arxii", "0197_legendlevelcalibration")]

    operations = [
        migrations.RenameModel(
            old_name="CharacterTitle",
            new_name="PersonaTitle",
        ),
        migrations.RemoveConstraint(
            model_name="personatitle",
            name="unique_character_title",
        ),
        migrations.AddField(
            model_name="personatitle",
            name="persona",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="titles",
                to="arxii.persona",
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="personatitle",
            name="persona",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="titles",
                to="arxii.persona",
            ),
        ),
        migrations.RemoveField(
            model_name="personatitle",
            name="character_sheet",
        ),
        migrations.AlterField(
            model_name="personatitle",
            name="reward",
            field=models.ForeignKey(
                blank=True,
                help_text="The TITLE-type RewardDefinition this title comes from.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="persona_titles",
                to="arxii.rewarddefinition",
            ),
        ),
        migrations.AddField(
            model_name="personatitle",
            name="legend_entry",
            field=models.ForeignKey(
                blank=True,
                help_text="The deed whose name this title is (#3466).",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="titles",
                to="arxii.legendentry",
            ),
        ),
        migrations.AlterModelOptions(
            name="personatitle",
            options={"ordering": ["persona", "reward", "legend_entry"]},
        ),
        migrations.AddConstraint(
            model_name="personatitle",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("legend_entry__isnull", True), ("reward__isnull", False)),
                    models.Q(("legend_entry__isnull", False), ("reward__isnull", True)),
                    _connector="OR",
                ),
                name="personatitle_exactly_one_source",
            ),
        ),
        migrations.AddConstraint(
            model_name="personatitle",
            constraint=models.UniqueConstraint(
                condition=models.Q(("reward__isnull", False)),
                fields=("persona", "reward"),
                name="unique_persona_reward_title",
            ),
        ),
        migrations.AddConstraint(
            model_name="personatitle",
            constraint=models.UniqueConstraint(
                condition=models.Q(("legend_entry__isnull", False)),
                fields=("persona", "legend_entry"),
                name="unique_persona_deed_title",
            ),
        ),
    ]
