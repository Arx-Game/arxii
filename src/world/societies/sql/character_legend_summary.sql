-- Materialized view: total personal legend per character across all personas.
-- Used for fast legend total lookups for Path advancement thresholds.
--
-- CAVEAT: After a migration squash, you must manually add a RunSQL operation
-- pointing at this file. Django's makemigrations won't auto-generate it.
--
-- Note: character_sheet_id equals character_id since CharacterSheet shares pk
-- with ObjectDB.
--
-- Source tables are arxii_persona / arxii_legendentry / arxii_legendspread
-- (single-app collapse, #2906) -- the view's own name stays
-- societies_characterlegendsummary since it's a managed=False model with an
-- explicit Meta.db_table, unaffected by the app-label table rename.

CREATE MATERIALIZED VIEW IF NOT EXISTS societies_characterlegendsummary AS
SELECT
    p.character_sheet_id AS character_id,
    COALESCE(SUM(
        CASE WHEN le.is_active THEN
            le.base_value + COALESCE(spread_totals.total_spread, 0)
        ELSE 0 END
    ), 0)::integer AS personal_legend
FROM arxii_persona p
LEFT JOIN arxii_legendentry le ON le.persona_id = p.id
LEFT JOIN (
    SELECT legend_entry_id, SUM(value_added) AS total_spread
    FROM arxii_legendspread
    GROUP BY legend_entry_id
) spread_totals ON spread_totals.legend_entry_id = le.id
GROUP BY p.character_sheet_id;

CREATE UNIQUE INDEX IF NOT EXISTS societies_characterlegendsummary_character_id
    ON societies_characterlegendsummary (character_id);
