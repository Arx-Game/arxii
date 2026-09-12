from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Anchor every interaction thread on the row it answers (#3787).

    Hand-written for one reason: the two anchor columns are NOT NULL, and
    ``makemigrations`` can only add a non-nullable column by inventing a one-off
    default to stamp on existing rows. There is no honest default here - an
    ``anchor_interaction_id`` of 0 names no interaction - so the columns are added
    nullable and immediately altered to NOT NULL instead. On an empty table that is
    the same end state; on a populated one it fails loudly on the ALTER rather than
    quietly writing a fabricated anchor into a real row.

    Nothing to backfill: ``arxii_interactionthread`` holds zero rows in production
    (checked against the dump, not assumed), so no row exists to carry across, and
    this migration stays schema-only.
    """

    dependencies = [
        ("arxii", "0133_normalize_trust_required_access_level"),
    ]

    operations = [
        migrations.AddField(
            model_name="interactionthread",
            name="anchor_interaction",
            field=models.ForeignKey(
                db_constraint=False,
                help_text=(
                    "The interaction every row in this thread answers. Required: a "
                    "thread exists only because someone answered a row, so there is no "
                    "such thing as an anchor-less one."
                ),
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="anchored_threads",
                to="arxii.interaction",
            ),
        ),
        migrations.AddField(
            model_name="interactionthread",
            name="anchor_timestamp",
            field=models.DateTimeField(
                help_text=(
                    "Denormalized from anchor_interaction - arxii_interaction is range-"
                    "partitioned on timestamp with a composite primary key, so a "
                    "single-column FK to its id cannot exist (the InteractionReceiver "
                    "precedent)."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="interactionthread",
            name="root",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Denormalized top of the nesting tree, so a reader groups an "
                    "exchange without walking parents. Null when this thread IS the "
                    "root."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="descendant_threads",
                to="arxii.interactionthread",
            ),
        ),
        migrations.AlterField(
            model_name="interactionthread",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "The thread the anchor row itself belongs to, when the anchor is a "
                    "reply. Null when the anchor is not a reply, which makes this "
                    "thread a root."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="child_threads",
                to="arxii.interactionthread",
            ),
        ),
        migrations.AlterField(
            model_name="interactionthread",
            name="anchor_interaction",
            field=models.ForeignKey(
                db_constraint=False,
                help_text=(
                    "The interaction every row in this thread answers. Required: a "
                    "thread exists only because someone answered a row, so there is no "
                    "such thing as an anchor-less one."
                ),
                on_delete=django.db.models.deletion.CASCADE,
                related_name="anchored_threads",
                to="arxii.interaction",
            ),
        ),
        migrations.AlterField(
            model_name="interactionthread",
            name="anchor_timestamp",
            field=models.DateTimeField(
                help_text=(
                    "Denormalized from anchor_interaction - arxii_interaction is range-"
                    "partitioned on timestamp with a composite primary key, so a "
                    "single-column FK to its id cannot exist (the InteractionReceiver "
                    "precedent)."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name="interactionthread",
            constraint=models.UniqueConstraint(
                fields=("anchor_interaction", "anchor_timestamp"),
                name="unique_thread_per_anchor",
            ),
        ),
        migrations.AddConstraint(
            model_name="interactionthread",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("parent__isnull", True),
                        models.Q(("parent", models.F("id")), _negated=True),
                        _connector="OR",
                    ),
                    models.Q(
                        ("root__isnull", True),
                        models.Q(("root", models.F("id")), _negated=True),
                        _connector="OR",
                    ),
                ),
                name="interaction_thread_no_self_nesting",
            ),
        ),
    ]
