-- Composite references for metadata attached to the partitioned Interaction table.
--
-- Interaction's primary key is (id, timestamp), so a single interaction_id
-- cannot guarantee integrity or cascade cleanup. This file is applied by
-- tools/build_schema.py after partition_interaction_forward.sql; migration
-- 0149 mirrors it for migration replay. PoseSubmission permits both reference
-- columns to be NULL for accepted ephemeral poses.

ALTER TABLE arxii_interactionreadreceipt
    ADD CONSTRAINT interactionreadreceipt_interaction_fk
    FOREIGN KEY (interaction_id, "timestamp")
    REFERENCES arxii_interaction (id, "timestamp")
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX interactionreadreceipt_interaction_ts_idx
    ON arxii_interactionreadreceipt (interaction_id, "timestamp");

ALTER TABLE arxii_posesubmission
    ADD CONSTRAINT posesubmission_interaction_fk
    FOREIGN KEY (interaction_id, "timestamp")
    REFERENCES arxii_interaction (id, "timestamp")
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX posesubmission_interaction_ts_fk_idx
    ON arxii_posesubmission (interaction_id, "timestamp");
