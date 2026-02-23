-- Materialized view: pre-computed breadcrumb paths for codex subjects.
-- Used for efficient breadcrumb display without recursive queries at read time.
--
-- CAVEAT: After a migration squash, you must manually add a RunSQL operation
-- pointing at this file. Django's makemigrations won't auto-generate it.
-- See docs/plans/2026-02-22-materialized-view-sql-files-design.md

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
