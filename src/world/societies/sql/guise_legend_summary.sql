-- Materialized view: total legend per persona (identity).
-- Used for fast legend total lookups per persona identity.
--
-- CAVEAT: After a migration squash, you must manually add a RunSQL operation
-- pointing at this file. Django's makemigrations won't auto-generate it.

CREATE MATERIALIZED VIEW IF NOT EXISTS societies_personalegendsummary AS
SELECT
    p.id AS persona_id,
    COALESCE(SUM(
        CASE WHEN le.is_active THEN
            le.base_value + COALESCE(spread_totals.total_spread, 0)
        ELSE 0 END
    ), 0)::integer AS persona_legend
FROM scenes_persona p
LEFT JOIN societies_legendentry le ON le.persona_id = p.id
LEFT JOIN (
    SELECT legend_entry_id, SUM(value_added) AS total_spread
    FROM societies_legendspread
    GROUP BY legend_entry_id
) spread_totals ON spread_totals.legend_entry_id = le.id
GROUP BY p.id;

CREATE UNIQUE INDEX IF NOT EXISTS societies_personalegendsummary_persona_id
    ON societies_personalegendsummary (persona_id);
