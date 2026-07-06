# Generated for #1919 — generalize SceneCastPullDeclaration → SceneActionPullDeclaration.
# Renames the model (data-preserving) and adds the charged_at / charged_flat_bonus
# idempotency fields used by the social-action pull charge path.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("magic", "0015_aurapowerconfig"),
        ("scenes", "0046_sceneunseenobserver"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="SceneCastPullDeclaration",
            new_name="SceneActionPullDeclaration",
        ),
        migrations.AlterField(
            model_name="sceneactionpulldeclaration",
            name="request",
            field=models.OneToOneField(
                help_text="The action request this pull was declared with.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pull_declaration",
                to="scenes.sceneactionrequest",
            ),
        ),
        migrations.AlterField(
            model_name="sceneactionpulldeclaration",
            name="threads",
            field=models.ManyToManyField(
                help_text="Threads pulled; owned by the actor, sharing ``resonance``.",
                related_name="action_pull_declarations",
                to="magic.thread",
            ),
        ),
        migrations.AddField(
            model_name="sceneactionpulldeclaration",
            name="charged_at",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text="When the pull was first charged at resolution time; guards "
                "against double-charging across multi-target resolutions (#1919).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="sceneactionpulldeclaration",
            name="charged_flat_bonus",
            field=models.IntegerField(
                blank=True,
                default=None,
                help_text="Cached FLAT_BONUS total from the first charge, returned on "
                "idempotent subsequent calls without re-charging (#1919).",
                null=True,
            ),
        ),
    ]
