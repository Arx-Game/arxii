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
    sequence_number integer NOT NULL,
    character_id bigint NOT NULL REFERENCES objects_objectdb (id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    location_id  bigint NOT NULL REFERENCES objects_objectdb (id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    persona_id   bigint REFERENCES scenes_persona (id)
        ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED,
    roster_entry_id bigint NOT NULL REFERENCES roster_rosterentry (id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    scene_id     bigint REFERENCES scenes_scene (id)
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
CREATE INDEX scenes_inte_charact_8f8da2_idx
    ON scenes_interaction (character_id, "timestamp");
CREATE INDEX scenes_inte_locatio_644746_idx
    ON scenes_interaction (location_id, "timestamp");
CREATE INDEX scenes_inte_scene_i_ffcd83_idx
    ON scenes_interaction (scene_id, sequence_number);
CREATE INDEX scenes_inte_roster__d2fc52_idx
    ON scenes_interaction (roster_entry_id, "timestamp");
CREATE INDEX interaction_loc_seq_desc_idx
    ON scenes_interaction (location_id, sequence_number DESC);
CREATE INDEX interaction_very_private_idx
    ON scenes_interaction ("timestamp")
    WHERE visibility = 'very_private';
CREATE INDEX interaction_no_scene_idx
    ON scenes_interaction (location_id, "timestamp")
    WHERE scene_id IS NULL;

-- 6. Drop composite FK constraints from child tables (added in forward)
ALTER TABLE scenes_interactionaudience
    DROP CONSTRAINT IF EXISTS interactionaudience_interaction_fk;
ALTER TABLE scenes_interactionfavorite
    DROP CONSTRAINT IF EXISTS interactionfavorite_interaction_fk;
ALTER TABLE scenes_interactiontargetpersona
    DROP CONSTRAINT IF EXISTS interactiontargetpersona_interaction_fk;

-- 7. Re-add single-column FK constraints
ALTER TABLE scenes_interactionaudience
    ADD CONSTRAINT scenes_interactionaudience_interaction_id_fk
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

-- 8. Drop BRIN indexes
DROP INDEX IF EXISTS interaction_ts_brin;
DROP INDEX IF EXISTS interactionaudience_ts_real_brin;
DROP INDEX IF EXISTS interactionfavorite_ts_brin;
DROP INDEX IF EXISTS interactiontargetpersona_ts_brin;
