-- Materialized view: total personal legend per character across all guises.
-- Used for fast legend total lookups for Path advancement thresholds.
--
-- CAVEAT: After a migration squash, you must manually add a RunSQL operation
-- pointing at this file. Django's makemigrations won't auto-generate it.

CREATE MATERIALIZED VIEW IF NOT EXISTS societies_characterlegendsummary AS
SELECT
    g.character_id,
    COALESCE(SUM(
        CASE WHEN le.is_active THEN
            le.base_value + COALESCE(spread_totals.total_spread, 0)
        ELSE 0 END
    ), 0)::integer AS personal_legend
FROM character_sheets_guise g
LEFT JOIN societies_legendentry le ON le.guise_id = g.id
LEFT JOIN (
    SELECT legend_entry_id, SUM(value_added) AS total_spread
    FROM societies_legendspread
    GROUP BY legend_entry_id
) spread_totals ON spread_totals.legend_entry_id = le.id
GROUP BY g.character_id;

CREATE UNIQUE INDEX IF NOT EXISTS societies_characterlegendsummary_character_id
    ON societies_characterlegendsummary (character_id);
