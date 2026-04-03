"""Rename character → character_sheet on DevelopmentPoints, DevelopmentTransaction, WeeklySkillUsage."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("progression", "0004_randomscenecompletion_randomscenetarget"),
        ("character_sheets", "0001_initial"),
    ]

    operations = [
        # DevelopmentPoints: rename character → character_sheet, add rust_debt
        migrations.RenameField(
            model_name="developmentpoints",
            old_name="character",
            new_name="character_sheet",
        ),
        migrations.AlterField(
            model_name="developmentpoints",
            name="character_sheet",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="development_points",
                to="character_sheets.charactersheet",
            ),
        ),
        migrations.AddField(
            model_name="developmentpoints",
            name="rust_debt",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Rust debt that must be paid off before dp counts toward advancement",
            ),
        ),
        # DevelopmentTransaction: rename character → character_sheet
        migrations.RenameField(
            model_name="developmenttransaction",
            old_name="character",
            new_name="character_sheet",
        ),
        migrations.AlterField(
            model_name="developmenttransaction",
            name="character_sheet",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="development_transactions",
                to="character_sheets.charactersheet",
            ),
        ),
        # Update DevelopmentTransaction source choices
        migrations.AlterField(
            model_name="developmenttransaction",
            name="source",
            field=models.CharField(
                choices=[
                    ("scene", "Scene Participation"),
                    ("training", "Training Activity"),
                    ("practice", "Practice Session"),
                    ("teaching", "Teaching Others"),
                    ("quest", "Quest Completion"),
                    ("exploration", "Exploration"),
                    ("crafting", "Crafting Activity"),
                    ("combat", "Combat Encounter"),
                    ("social", "Social Activity"),
                    ("rust", "Skill Rust"),
                    ("other", "Other Activity"),
                ],
                max_length=20,
            ),
        ),
        # Create WeeklySkillUsage
        migrations.CreateModel(
            name="WeeklySkillUsage",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("week_start", models.DateField()),
                ("points_earned", models.PositiveIntegerField(default=0)),
                ("check_count", models.PositiveIntegerField(default=0)),
                ("processed", models.BooleanField(default=False)),
                (
                    "character_sheet",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="weekly_skill_usage",
                        to="character_sheets.charactersheet",
                    ),
                ),
                (
                    "trait",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="weekly_skill_usage",
                        to="traits.trait",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddConstraint(
            model_name="weeklyskillusage",
            constraint=models.UniqueConstraint(
                fields=("character_sheet", "trait", "week_start"),
                name="unique_skill_usage_per_week",
            ),
        ),
        # Update unique_together and indexes for DevelopmentPoints
        migrations.AlterUniqueTogether(
            name="developmentpoints",
            unique_together={("character_sheet", "trait")},
        ),
    ]
