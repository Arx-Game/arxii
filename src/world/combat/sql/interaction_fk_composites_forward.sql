-- Composite FK constraints from combat tables onto the partitioned
-- arxii_interaction (id, timestamp). Mirrors the constraints added in
-- scenes/sql/partition_interaction_forward.sql for InteractionReceiver et al.
--
-- Both Django FKs were declared db_constraint=False on the model side because
-- the partitioned target table requires a composite FK on (id, timestamp).
-- These constraints are DEFERRABLE INITIALLY DEFERRED so the round-resolve
-- write path can set interaction_id + interaction_timestamp in the same
-- save() / transaction without ordering concerns.
--
-- Applied by: src/world/migrations/0109_partition_interaction.py (RunSQL), and
-- listed in tools/build_schema.py's SQL_FILES so CI, the parity tier, and the
-- devcontainer apply it too (#2982 restored both after the #2906 single-app
-- collapse's plain makemigrations silently dropped the RunSQL step).

ALTER TABLE arxii_combatroundaction
    ADD CONSTRAINT combat_roundaction_interaction_fk
    FOREIGN KEY (interaction_id, interaction_timestamp)
    REFERENCES arxii_interaction (id, "timestamp")
    ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE arxii_clashcontribution
    ADD CONSTRAINT combat_clashcontribution_interaction_fk
    FOREIGN KEY (interaction_id, interaction_timestamp)
    REFERENCES arxii_interaction (id, "timestamp")
    ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
