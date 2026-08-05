-- Reverse of interaction_fk_composites_forward.sql.
-- Drops the composite FK constraints that link combat round-action and
-- clash-contribution rows to the partitioned arxii_interaction table.
--
-- Applied by: src/world/migrations/0108_partition_interaction.py, as the
-- reverse_sql of the RunSQL that applies interaction_fk_composites_forward.sql.
-- Not listed in tools/build_schema.py's SQL_FILES - build_schema.py builds
-- forward-only from models, so reverse files have no direction to satisfy there.

ALTER TABLE arxii_clashcontribution
    DROP CONSTRAINT IF EXISTS combat_clashcontribution_interaction_fk;

ALTER TABLE arxii_combatroundaction
    DROP CONSTRAINT IF EXISTS combat_roundaction_interaction_fk;
