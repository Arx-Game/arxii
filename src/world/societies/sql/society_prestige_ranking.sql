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

-- Fame tier multipliers from world.societies.constants.FAME_TIER_MULTIPLIERS,
-- and the tier-ordering used for fame_perception_offset application (#738).
-- Hard-coded here (single source of truth in the Python constants file).
-- If the multipliers / order move to DB-backed lookups, replace these CTEs
-- with JOINs against those tables.
CREATE MATERIALIZED VIEW IF NOT EXISTS societies_societyprestigeranking AS
WITH fame_tier_ranks AS (
    -- 0-based tier indices. Matches FAME_TIER_ORDER. Used to apply
    -- per-society fame_perception_offset (≤0): the displayed tier in
    -- a society's ranking is max(0, tier_index + society.offset).
    SELECT 'normal'         AS fame_tier, 0 AS tier_index
    UNION ALL SELECT 'talked_about',    1
    UNION ALL SELECT 'celebrity',       2
    UNION ALL SELECT 'household_name',  3
    UNION ALL SELECT 'world_famous',    4
),
fame_multipliers AS (
    SELECT 0 AS tier_index, 1.0::numeric  AS multiplier
    UNION ALL SELECT 1, 1.25
    UNION ALL SELECT 2, 2.5
    UNION ALL SELECT 3, 5.0
    UNION ALL SELECT 4, 10.0
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
        -- displayed_prestige = total_prestige × multiplier(persona's tier
        -- minus this society's fame_perception_offset, floored at 0),
        -- clamped at 0. #738.
        GREATEST(
            0,
            FLOOR(
                p.total_prestige
                * COALESCE(adj_fm.multiplier, 1.0)
            )
        )::integer AS displayed_prestige
    FROM persona_membership_societies pms
    JOIN scenes_persona p ON p.id = pms.persona_id
    JOIN societies_society s ON s.id = pms.society_id
    LEFT JOIN fame_tier_ranks ftr ON ftr.fame_tier = p.fame_tier
    LEFT JOIN fame_multipliers adj_fm ON adj_fm.tier_index =
        GREATEST(0, COALESCE(ftr.tier_index, 0) + COALESCE(s.fame_perception_offset, 0))
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
