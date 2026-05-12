-- Materialized view: total legend per covenant, summing base_value + spreads
-- across all CovenantLegendCredit rows linked to that covenant.
--
-- Used for fast covenant legend total lookups (e.g., level advancement).
-- Refreshed via refresh_legend_views() after any mutation to legend data.
--
-- CAVEAT: After a migration squash, you must manually add a RunSQL operation
-- pointing at this file. Django's makemigrations won't auto-generate it.
--
-- REFRESH MATERIALIZED VIEW CONCURRENTLY requires a unique index — hence both
-- statements below.

CREATE MATERIALIZED VIEW IF NOT EXISTS societies_covenantlegendsummary AS
SELECT
    c.id AS covenant_id,
    COALESCE(SUM(
        CASE WHEN le.is_active THEN
            le.base_value + COALESCE(spreads.total, 0)
        ELSE 0 END
    ), 0)::bigint AS legend_total
FROM covenants_covenant c
LEFT JOIN societies_covenantlegendcredit clc ON clc.covenant_id = c.id
LEFT JOIN societies_legendentry le ON le.id = clc.entry_id
LEFT JOIN (
    SELECT legend_entry_id, SUM(value_added)::bigint AS total
    FROM societies_legendspread
    GROUP BY legend_entry_id
) spreads ON spreads.legend_entry_id = le.id
GROUP BY c.id;

CREATE UNIQUE INDEX IF NOT EXISTS societies_covenantlegendsummary_covenant_id_idx
    ON societies_covenantlegendsummary (covenant_id);
