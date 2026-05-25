-- Reverse of interaction_fk_composites_forward.sql.
-- Drops the composite FK constraints that link combat round-action and
-- clash-contribution rows to the partitioned scenes_interaction table.

ALTER TABLE combat_clashcontribution
    DROP CONSTRAINT IF EXISTS combat_clashcontribution_interaction_fk;

ALTER TABLE combat_combatroundaction
    DROP CONSTRAINT IF EXISTS combat_roundaction_interaction_fk;
