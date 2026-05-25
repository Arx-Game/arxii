-- Composite FK constraints from combat tables onto the partitioned
-- scenes_interaction (id, timestamp). Mirrors the constraints added in
-- scenes/sql/partition_interaction_forward.sql for InteractionReceiver et al.
--
-- Both Django FKs were declared db_constraint=False on the model side because
-- the partitioned target table requires a composite FK on (id, timestamp).
-- These constraints are DEFERRABLE INITIALLY DEFERRED so the round-resolve
-- write path can set interaction_id + interaction_timestamp in the same
-- save() / transaction without ordering concerns.
--
-- Referenced by: combat/migrations/0004_interaction_fk_composites.py.
-- If migrations are squashed, this SQL file must be preserved and re-referenced.

ALTER TABLE combat_combatroundaction
    ADD CONSTRAINT combat_roundaction_interaction_fk
    FOREIGN KEY (interaction_id, interaction_timestamp)
    REFERENCES scenes_interaction (id, "timestamp")
    ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE combat_clashcontribution
    ADD CONSTRAINT combat_clashcontribution_interaction_fk
    FOREIGN KEY (interaction_id, interaction_timestamp)
    REFERENCES scenes_interaction (id, "timestamp")
    ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
