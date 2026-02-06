# Generated manually

from django.db import migrations, models


def migrate_content_to_lore(apps, schema_editor):
    """Migrate existing content field data to lore_content."""
    CodexEntry = apps.get_model("codex", "CodexEntry")
    for entry in CodexEntry.objects.all():
        entry.lore_content = entry.content
        entry.save(update_fields=["lore_content"])


def migrate_lore_to_content(apps, schema_editor):
    """Reverse: migrate lore_content back to content."""
    CodexEntry = apps.get_model("codex", "CodexEntry")
    for entry in CodexEntry.objects.all():
        entry.content = entry.lore_content or ""
        entry.save(update_fields=["content"])


class Migration(migrations.Migration):
    dependencies = [
        ("codex", "0005_clue_models_and_status_rename"),
    ]

    operations = [
        # Step 1: Add the new fields (lore_content and mechanics_content)
        migrations.AddField(
            model_name="codexentry",
            name="lore_content",
            field=models.TextField(
                blank=True,
                null=True,
                help_text="In-character world flavor/lore content.",
            ),
        ),
        migrations.AddField(
            model_name="codexentry",
            name="mechanics_content",
            field=models.TextField(
                blank=True,
                null=True,
                help_text="Out-of-character mechanical explanation.",
            ),
        ),
        # Step 2: Migrate data from content to lore_content
        migrations.RunPython(
            migrate_content_to_lore,
            migrate_lore_to_content,
        ),
        # Step 3: Remove the old content field
        migrations.RemoveField(
            model_name="codexentry",
            name="content",
        ),
    ]
