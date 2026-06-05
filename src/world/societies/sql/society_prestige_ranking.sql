-- #676 Phase I — Society prestige ranking materialized view.
-- One row per (society, persona) with displayed_prestige (total × tier
-- multiplier) and dense rank within the society.
--
-- Per-society rankings are computed for every persona that has at least
-- one membership in an organization belonging to that society. Personas
-- with no membership in a society don't appear in that society's
-- ranking — they're not "of" that society in any meaningful sense.
--
-- Refresh nightly via REFRESH MATERIALIZED VIEW CONCURRENTLY
-- societies_societyprestigeranking; (CONCURRENTLY requires the
-- unique index below to exist).
--
-- CAVEAT: After a migration squash, add a RunSQL operation pointing at
-- this file. Django's makemigrations won't auto-generate it.

-- Fame tier multipliers from world.societies.constants.FAME_TIER_MULTIPLIERS.
-- Hard-coded here (single source of truth in the Python constants file).
-- If the multipliers move to a DB-backed lookup, replace this CTE with a
-- JOIN against that table.
CREATE MATERIALIZED VIEW IF NOT EXISTS societies_societyprestigeranking AS
WITH fame_multipliers AS (
    SELECT 'normal'         AS fame_tier, 1.0::numeric  AS multiplier
    UNION ALL SELECT 'talked_about',     1.25
    UNION ALL SELECT 'celebrity',        2.5
    UNION ALL SELECT 'household_name',   5.0
    UNION ALL SELECT 'world_famous',     10.0
),
persona_membership_societies AS (
    -- Every (persona, society) pair where the persona has at least one
    -- org membership in an organization belonging to that society.
    SELECT DISTINCT
        om.persona_id,
        org.society_id
    FROM societies_organizationmembership om
    JOIN societies_organization org ON org.id = om.organization_id
    WHERE org.society_id IS NOT NULL
),
displayed AS (
    SELECT
        pms.society_id,
        pms.persona_id AS persona_id,
        -- displayed_prestige = total_prestige × fame_tier_multiplier
        -- clamped at 0. Default multiplier 1.0 if tier missing from
        -- the lookup (defensive — shouldn't happen with valid data).
        GREATEST(
            0,
            FLOOR(p.total_prestige * COALESCE(fm.multiplier, 1.0))
        )::integer AS displayed_prestige
    FROM persona_membership_societies pms
    JOIN scenes_persona p ON p.id = pms.persona_id
    LEFT JOIN fame_multipliers fm ON fm.fame_tier = p.fame_tier
)
SELECT
    -- pk surrogate so SharedMemoryModel can identity-map this row.
    ROW_NUMBER() OVER () AS id,
    d.society_id,
    d.persona_id,
    d.displayed_prestige,
    DENSE_RANK() OVER (
        PARTITION BY d.society_id ORDER BY d.displayed_prestige DESC
    )::integer AS rank
FROM displayed d;

CREATE UNIQUE INDEX IF NOT EXISTS
    societies_societyprestigeranking_society_persona_idx
    ON societies_societyprestigeranking (society_id, persona_id);

CREATE INDEX IF NOT EXISTS
    societies_societyprestigeranking_society_rank_idx
    ON societies_societyprestigeranking (society_id, rank);
