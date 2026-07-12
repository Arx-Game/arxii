# Non-secret. Feed these into the PROD root's S3-compatible backend config.
# The backend ACCESS KEY/SECRET are NOT outputs here — they are created
# manually by the operator (see README) so no credential enters this state.

output "state_bucket" {
  value       = linode_object_storage_bucket.state.label
  description = "Bucket name to use as the prod Terraform backend bucket."
}

output "state_region" {
  value       = var.region
  description = "Region of the state bucket."
}

output "state_s3_endpoint" {
  # `${region}.linodeobjects.com` is not a real host (real endpoints are
  # cluster-suffixed, e.g. `us-east-1.linodeobjects.com`). Use the bucket
  # resource's own `s3_endpoint` attribute instead of guessing the hostname
  # pattern — verified against the pinned linode provider (2.41.2), repo
  # linode/terraform-provider-linode, tag v2.41.2:
  #   linode/objbucket/schema_resource.go — `s3_endpoint` (not the
  #     deprecated `endpoint`) is the current computed S3 endpoint attr.
  #   linode/helper/objects.go (ComputeS3EndpointFromBucket) — resolves to
  #     a bare hostname (bucket Hostname minus the label prefix), so
  #     `https://` is prefixed here.
  value       = "https://${linode_object_storage_bucket.state.s3_endpoint}"
  description = "S3-compatible endpoint for the prod backend block."
}
