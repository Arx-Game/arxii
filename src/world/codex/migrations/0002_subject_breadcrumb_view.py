"""Materialized view for pre-computed codex subject breadcrumb paths."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("codex", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE MATERIALIZED VIEW codex_subjectbreadcrumb AS
                WITH RECURSIVE path_cte AS (
                    -- Base: top-level subjects (no parent)
                    SELECT
                        s.id AS subject_id,
                        jsonb_build_array(
                            jsonb_build_object(
                                'type', 'category', 'id', s.category_id, 'name', c.name
                            ),
                            jsonb_build_object(
                                'type', 'subject', 'id', s.id, 'name', s.name
                            )
                        ) AS breadcrumb_path
                    FROM codex_codexsubject s
                    JOIN codex_codexcategory c ON c.id = s.category_id
                    WHERE s.parent_id IS NULL

                    UNION ALL

                    -- Recursive: children append themselves to parent path
                    SELECT
                        s.id AS subject_id,
                        p.breadcrumb_path || jsonb_build_array(
                            jsonb_build_object(
                                'type', 'subject', 'id', s.id, 'name', s.name
                            )
                        )
                    FROM codex_codexsubject s
                    JOIN path_cte p ON p.subject_id = s.parent_id
                )
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    subject_id,
                    breadcrumb_path
                FROM path_cte;

                CREATE UNIQUE INDEX codex_subjectbreadcrumb_subject_idx
                    ON codex_subjectbreadcrumb (subject_id);
                CREATE UNIQUE INDEX codex_subjectbreadcrumb_id_idx
                    ON codex_subjectbreadcrumb (id);
            """,
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS codex_subjectbreadcrumb;",
        ),
        # Register CodexSubjectBreadcrumb as an unmanaged model so Django
        # tracks it in migration state. The actual view is created by RunSQL above.
        migrations.CreateModel(
            name="CodexSubjectBreadcrumb",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "subject",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="breadcrumb_cache",
                        to="codex.codexsubject",
                    ),
                ),
                ("breadcrumb_path", models.JSONField()),
            ],
            options={
                "db_table": "codex_subjectbreadcrumb",
                "managed": False,
            },
        ),
    ]
