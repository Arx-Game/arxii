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

CREATE MATERIALIZED VIEW IF NOT EXISTS societies_societyprestigeranking AS
WITH persona_membership_societies AS (
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
        GREATEST(0, p.total_prestige) AS displayed_prestige
    FROM persona_membership_societies pms
    JOIN scenes_persona p ON p.id = pms.persona_id
)
SELECT
    -- pk surrogate so SharedMemoryModel can identity-map this row.
    ROW_NUMBER() OVER () AS id,
    d.society_id,
    d.persona_id,
    d.displayed_prestige::integer,
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
