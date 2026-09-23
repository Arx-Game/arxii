"""Keep partition metadata references explicit in Django's model state.

Django cannot emit a database foreign key to the composite Interaction
candidate key. The physical columns and PostgreSQL composite constraints
already exist; this state-only migration removes the old scalar ForeignKey
state without touching those columns or constraints. Runtime models expose an
ORM-only ForeignObject relation whose DO_NOTHING policy leaves cleanup to the
PostgreSQL composite constraint.
"""

from django.db import migrations, models
from django.db.models import Q

import world.scenes.fields


class Migration(migrations.Migration):
    dependencies = [("arxii", "0150_partitioned_metadata_fk")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="interactionreadreceipt",
                    name="unique_read_receipt_per_account",
                ),
                migrations.RemoveConstraint(
                    model_name="posesubmission",
                    name="pose_submission_interaction_timestamp_pair",
                ),
                migrations.RemoveIndex(
                    model_name="posesubmission",
                    name="posesub_interaction_ts_idx",
                ),
                migrations.RemoveField(
                    model_name="interactionreadreceipt",
                    name="interaction",
                ),
                migrations.RemoveField(
                    model_name="posesubmission",
                    name="interaction",
                ),
                migrations.AddField(
                    model_name="interactionreadreceipt",
                    name="interaction_id",
                    field=models.BigIntegerField(help_text="The pose marked read"),
                ),
                migrations.AddField(
                    model_name="posesubmission",
                    name="interaction_id",
                    field=models.BigIntegerField(
                        blank=True,
                        help_text="The Interaction id this submission produced.",
                        null=True,
                    ),
                ),
                migrations.AddField(
                    model_name="interactionreadreceipt",
                    name="interaction",
                    field=world.scenes.fields.CompositeForeignKey(
                        from_fields=("interaction_id", "timestamp"),
                        on_delete=models.DO_NOTHING,
                        related_name="read_receipts",
                        to="arxii.Interaction",
                        to_fields=("id", "timestamp"),
                    ),
                ),
                migrations.AddField(
                    model_name="posesubmission",
                    name="interaction",
                    field=world.scenes.fields.CompositeForeignKey(
                        from_fields=("interaction_id", "timestamp"),
                        on_delete=models.DO_NOTHING,
                        related_name="pose_submissions",
                        to="arxii.Interaction",
                        to_fields=("id", "timestamp"),
                    ),
                ),
                migrations.AddIndex(
                    model_name="posesubmission",
                    index=models.Index(
                        fields=["interaction_id", "timestamp"],
                        name="posesub_interaction_ts_idx",
                    ),
                ),
                migrations.AddConstraint(
                    model_name="interactionreadreceipt",
                    constraint=models.UniqueConstraint(
                        fields=("interaction_id", "timestamp", "account"),
                        name="unique_read_receipt_per_account",
                    ),
                ),
                migrations.AddConstraint(
                    model_name="posesubmission",
                    constraint=models.CheckConstraint(
                        check=(
                            Q(interaction_id__isnull=True, timestamp__isnull=True)
                            | Q(interaction_id__isnull=False, timestamp__isnull=False)
                        ),
                        name="pose_submission_interaction_timestamp_pair",
                    ),
                ),
            ],
            database_operations=[],
        )
    ]
