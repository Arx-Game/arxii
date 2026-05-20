# Terraform remote-state bootstrap (run ONCE, ever)

This creates the Linode Object Storage bucket that the **prod** root uses as
its remote backend. It cannot be part of the prod root (a backend can't store
the state of the bucket that *is* the backend), so it stands alone with **local
state**.

## One-time procedure

1. `export TF_VAR_linode_token=...` (operator-side; never committed, never on
   the box). `export TF_VAR_state_bucket_label=arxii-tfstate-<unique>`.
2. `cd infra/terraform/bootstrap && tofu init && tofu apply`
3. **Create the backend access key MANUALLY** (kept out of Tofu state on
   purpose): in the Linode console create an Object Storage access key
   scoped to *only* this state bucket; record it where the operator runs the
   button (env / CI secret) — it is operator/CI-only, never on the prod box.
4. Put `state_bucket`, `state_region`, `state_s3_endpoint` (the `tofu output`s)
   into the prod root's backend config.
5. `export TF_STATE_BOOTSTRAPPED=1` for `standup.sh`.

## Safety invariants

- **Versioning on, Object Lock OFF.** Never enable Object Lock on this bucket
  — the S3 backend rewrites state in place; a locked state object bricks every
  future `tofu apply`. (Object Lock is for the *backup* buckets only.)
- **`prevent_destroy` on.** Tofu will hard-error rather than destroy it.

## Recovery — local state lost

`bootstrap/terraform.tfstate` is the only record of this bucket and is **not**
committed (see `infra/terraform/.gitignore`). If it is lost, do NOT re-`apply`
blindly (it would try to create an existing bucket and error). Instead
re-adopt the existing bucket:

```
tofu init
tofu import linode_object_storage_bucket.state <region>:<state_bucket_label>
tofu plan   # expect: no changes
```

Confirm the exact import ID format against the pinned provider docs.
