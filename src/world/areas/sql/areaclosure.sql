-- Materialized view: transitive closure of the area hierarchy.
-- Used for efficient ancestor/descendant queries on the area tree.
--
-- CAVEAT: After a migration squash, you must manually add a RunSQL operation
-- pointing at this file. Django's makemigrations won't auto-generate it.
-- See docs/plans/2026-02-22-materialized-view-sql-files-design.md

CREATE MATERIALIZED VIEW areas_areaclosure AS
WITH RECURSIVE closure AS (
    SELECT id AS ancestor_id, id AS descendant_id, 0 AS depth
    FROM areas_area
    UNION ALL
    SELECT c.ancestor_id, a.id AS descendant_id, c.depth + 1
    FROM closure c
    JOIN areas_area a ON a.parent_id = c.descendant_id
)
SELECT
    ROW_NUMBER() OVER () AS id,
    ancestor_id,
    descendant_id,
    depth
FROM closure;

CREATE UNIQUE INDEX areas_areaclosure_id_idx
    ON areas_areaclosure (id);
CREATE INDEX areas_areaclosure_ancestor_idx
    ON areas_areaclosure (ancestor_id);
CREATE INDEX areas_areaclosure_descendant_idx
    ON areas_areaclosure (descendant_id);
CREATE INDEX areas_areaclosure_anc_desc_idx
    ON areas_areaclosure (ancestor_id, descendant_id);
