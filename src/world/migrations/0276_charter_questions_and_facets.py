# Rename only (#4532, ADR-4532-A): the house-side "aspect" becomes a charter question, its
# answer an option, a house's picked answer a facet. No data moves and nothing is dropped.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("arxii", "0275_secret_links_and_many_distinctions_per_secret")]

    operations = [
        migrations.RenameModel(old_name="HouseAspectDefinition", new_name="HouseCharterQuestion"),
        migrations.RenameModel(old_name="HouseAspectOption", new_name="HouseCharterOption"),
        migrations.RenameModel(old_name="HouseClaimAspect", new_name="HouseClaimFacet"),
        migrations.RenameModel(old_name="OrganizationAspect", new_name="OrganizationFacet"),
        migrations.RenameField(
            model_name="housetemplate",
            old_name="aspect_definitions",
            new_name="charter_questions",
        ),
        # The reverse accessors follow the rename (``claim.facets``, ``organization.facets``):
        # state only, no table change.
        migrations.AlterField(
            model_name="houseclaimfacet",
            name="claim",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="facets",
                to="arxii.houseclaim",
            ),
        ),
        migrations.AlterField(
            model_name="organizationfacet",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="facets",
                to="arxii.organization",
            ),
        ),
        # An option's own reverse accessors (``being.house_charter_options`` and so on).
        migrations.AlterField(
            model_name="housecharteroption",
            name="being",
            field=models.ForeignKey(
                blank=True,
                help_text="The god or totem this option is (#4205).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="house_charter_options",
                to="arxii.worshippedbeing",
            ),
        ),
        migrations.AlterField(
            model_name="housecharteroption",
            name="being_nickname",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "The name a house on this option calls the being by; one of the "
                    "being's own nicknames. Becomes the house's patron_nickname on a "
                    "patron question."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="house_charter_options",
                to="arxii.beingnickname",
            ),
        ),
        migrations.AlterField(
            model_name="housecharteroption",
            name="codex_entry",
            field=models.ForeignKey(
                blank=True,
                help_text="Lore entry this option is bound to, if any.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="house_charter_options",
                to="arxii.codexentry",
            ),
        ),
    ]
