-- Reverse: convert partitioned arxii_interaction back to a regular table.
--
-- Applied by: src/world/migrations/0109_partition_interaction.py, as the
-- reverse_sql of the RunSQL that applies partition_interaction_forward.sql.
-- Not listed in tools/build_schema.py's SQL_FILES - build_schema.py builds
-- forward-only from models, so reverse files have no direction to satisfy there.

-- 1. Rename partitioned table
ALTER TABLE arxii_interaction RENAME TO arxii_interaction_partitioned;

-- 2. Create regular table with same structure as the forward SQL's partitioned
-- table. The column list MUST match world.scenes.models.Interaction. Drift is
-- enforced by tools/check_partition_sql_drift.py (pre-commit hook).
-- ON DELETE NO ACTION mirrors the forward SQL (Postgres has no PROTECT — see
-- notes in partition_interaction_forward.sql).
CREATE TABLE arxii_interaction (
    id               bigserial PRIMARY KEY,
    content          text NOT NULL,
    mode             varchar(20) NOT NULL,
    visibility       varchar(20) NOT NULL,
    pose_kind        varchar(16) NOT NULL DEFAULT 'standard',
    vote_count            integer NOT NULL DEFAULT 0 CHECK (vote_count >= 0),
    strain_committed      integer NOT NULL DEFAULT 0 CHECK (strain_committed >= 0),
    -- NOTE: fury_committed_id is intentionally absent here -- see the matching
    -- note in partition_interaction_forward.sql. It is a post-partition column
    -- (FK to magic.FuryTier, added by scenes/0024). On reverse, the column was
    -- already dropped before this migration runs back, so re-adding it is not
    -- this SQL's job. See POST_PARTITION_COLUMNS in check_partition_sql_drift.py
    "timestamp"           timestamptz NOT NULL,
    persona_id            bigint NOT NULL REFERENCES arxii_persona (id)
        ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
    scene_id              bigint REFERENCES arxii_scene (id)
        ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED,
    place_id              bigint REFERENCES arxii_place (id)
        ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
);

-- 3. Copy data — explicit column list (drift-checked vs. the CREATE TABLE above)
INSERT INTO arxii_interaction
    (id, content, mode, visibility, pose_kind, vote_count, strain_committed, "timestamp", persona_id, scene_id, place_id)
    SELECT id, content, mode, visibility, pose_kind, vote_count, strain_committed, "timestamp", persona_id, scene_id, place_id
    FROM arxii_interaction_partitioned;

-- 4. Drop partitioned table
DROP TABLE arxii_interaction_partitioned CASCADE;

-- 5. Recreate indexes
CREATE INDEX arxii_interaction_timestamp_idx
    ON arxii_interaction ("timestamp");
CREATE INDEX arxii_inte_persona_ts_idx
    ON arxii_interaction (persona_id, "timestamp");
CREATE INDEX arxii_inte_scene_ts_idx
    ON arxii_interaction (scene_id, "timestamp");
CREATE INDEX interaction_very_private_idx
    ON arxii_interaction ("timestamp")
    WHERE visibility = 'very_private';
CREATE INDEX interaction_no_scene_idx
    ON arxii_interaction ("timestamp")
    WHERE scene_id IS NULL;

-- 6. Drop composite FK constraints from child tables (added in forward)
ALTER TABLE arxii_interactionreceiver
    DROP CONSTRAINT IF EXISTS interactionreceiver_interaction_fk;
ALTER TABLE arxii_interactionfavorite
    DROP CONSTRAINT IF EXISTS interactionfavorite_interaction_fk;
ALTER TABLE arxii_interactiontargetpersona
    DROP CONSTRAINT IF EXISTS interactiontargetpersona_interaction_fk;
ALTER TABLE arxii_interactionreaction
    DROP CONSTRAINT IF EXISTS interactionreaction_interaction_fk;

-- 7. Re-add single-column FK constraints
ALTER TABLE arxii_interactionreceiver
    ADD CONSTRAINT arxii_interactionreceiver_interaction_id_fk
    FOREIGN KEY (interaction_id) REFERENCES arxii_interaction (id)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE arxii_interactionfavorite
    ADD CONSTRAINT arxii_interactionfavorite_interaction_id_fk
    FOREIGN KEY (interaction_id) REFERENCES arxii_interaction (id)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE arxii_interactiontargetpersona
    ADD CONSTRAINT arxii_interactiontargetpersona_interaction_id_fk
    FOREIGN KEY (interaction_id) REFERENCES arxii_interaction (id)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE arxii_interactionreaction
    ADD CONSTRAINT arxii_interactionreaction_interaction_id_fk
    FOREIGN KEY (interaction_id) REFERENCES arxii_interaction (id)
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

-- 8. Drop BRIN indexes
DROP INDEX IF EXISTS interaction_ts_brin;
DROP INDEX IF EXISTS interactionreceiver_ts_brin;
DROP INDEX IF EXISTS interactionfavorite_ts_brin;
DROP INDEX IF EXISTS interactiontargetpersona_ts_brin;
DROP INDEX IF EXISTS interactionreaction_ts_brin;
