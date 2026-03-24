-- Reverse: convert partitioned scenes_interaction back to a regular table.
--
-- Referenced by: scenes/migrations/0003_partition_interaction.py
-- If migrations are squashed, this SQL file must be preserved and re-referenced.

-- 1. Rename partitioned table
ALTER TABLE scenes_interaction RENAME TO scenes_interaction_partitioned;

-- 2. Create regular table with same structure
CREATE TABLE scenes_interaction (
    id          bigserial PRIMARY KEY,
    content     text NOT NULL,
    mode        varchar(20) NOT NULL,
    visibility  varchar(20) NOT NULL,
    "timestamp" timestamptz NOT NULL,
    persona_id  bigint NOT NULL REFERENCES scenes_persona (id)
        ON DELETE PROTECT DEFERRABLE INITIALLY DEFERRED,
    scene_id    bigint REFERENCES scenes_scene (id)
        ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED,
    place_id    bigint REFERENCES scenes_place (id)
        ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
);

-- 3. Copy data
INSERT INTO scenes_interaction
    SELECT * FROM scenes_interaction_partitioned;

-- 4. Drop partitioned table
DROP TABLE scenes_interaction_partitioned CASCADE;

-- 5. Recreate indexes
CREATE INDEX scenes_interaction_timestamp_idx
    ON scenes_interaction ("timestamp");
CREATE INDEX scenes_inte_persona_ts_idx
    ON scenes_interaction (persona_id, "timestamp");
CREATE INDEX scenes_inte_scene_ts_idx
    ON scenes_interaction (scene_id, "timestamp");
CREATE INDEX interaction_very_private_idx
    ON scenes_interaction ("timestamp")
    WHERE visibility = 'very_private';
CREATE INDEX interaction_no_scene_idx
    ON scenes_interaction ("timestamp")
    WHERE scene_id IS NULL;

-- 6. Drop composite FK constraints from child tables (added in forward)
ALTER TABLE scenes_interactionreceiver
    DROP CONSTRAINT IF EXISTS interactionreceiver_interaction_fk;
ALTER TABLE scenes_interactionfavorite
    DROP CONSTRAINT IF EXISTS interactionfavorite_interaction_fk;
ALTER TABLE scenes_interactiontargetpersona
    DROP CONSTRAINT IF EXISTS interactiontargetpersona_interaction_fk;
ALTER TABLE scenes_interactionreaction
    DROP CONSTRAINT IF EXISTS interactionreaction_interaction_fk;

-- 7. Re-add single-column FK constraints
ALTER TABLE scenes_interactionreceiver
    ADD CONSTRAINT scenes_interactionreceiver_interaction_id_fk
    FOREIGN KEY (interaction_id) REFERENCES scenes_interaction (id)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE scenes_interactionfavorite
    ADD CONSTRAINT scenes_interactionfavorite_interaction_id_fk
    FOREIGN KEY (interaction_id) REFERENCES scenes_interaction (id)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE scenes_interactiontargetpersona
    ADD CONSTRAINT scenes_interactiontargetpersona_interaction_id_fk
    FOREIGN KEY (interaction_id) REFERENCES scenes_interaction (id)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE scenes_interactionreaction
    ADD CONSTRAINT scenes_interactionreaction_interaction_id_fk
    FOREIGN KEY (interaction_id) REFERENCES scenes_interaction (id)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

-- 8. Drop BRIN indexes
DROP INDEX IF EXISTS interaction_ts_brin;
DROP INDEX IF EXISTS interactionreceiver_ts_brin;
DROP INDEX IF EXISTS interactionfavorite_ts_brin;
DROP INDEX IF EXISTS interactiontargetpersona_ts_brin;
DROP INDEX IF EXISTS interactionreaction_ts_brin;
