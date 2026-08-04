-- Reverse of interaction_fk_composites_forward.sql.
-- Drops the composite FK constraints that link combat round-action and
-- clash-contribution rows to the partitioned arxii_interaction table.
--
-- Kept for reference only: no migration currently applies this reverse SQL
-- (the #2906 single-app collapse squashed the per-app migration chain that
-- used to RunSQL it; tools/build_schema.py builds forward-only from models).

ALTER TABLE arxii_clashcontribution
    DROP CONSTRAINT IF EXISTS combat_clashcontribution_interaction_fk;

ALTER TABLE arxii_combatroundaction
    DROP CONSTRAINT IF EXISTS combat_roundaction_interaction_fk;
