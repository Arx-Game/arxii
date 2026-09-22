-- Reverse for interaction_metadata_fk_forward.sql.
ALTER TABLE arxii_posesubmission
    DROP CONSTRAINT IF EXISTS posesubmission_interaction_fk;
DROP INDEX IF EXISTS posesubmission_interaction_ts_fk_idx;
ALTER TABLE arxii_interactionreadreceipt
    DROP CONSTRAINT IF EXISTS interactionreadreceipt_interaction_fk;
DROP INDEX IF EXISTS interactionreadreceipt_interaction_ts_idx;
