# Minimal: just a throwaway stage host (reuses the compute module WITHOUT its
# prevent_destroy intent mattering — stage is meant to be destroyed). No DNS,
# no backups, no prod refs: this root cannot enumerate or affect prod by
# construction (separate state + separate credential scope, §4.8). The
# scripted apply->test->destroy + the env=ephemeral-stage tag guard live in
# scripts/ (T25).
#
# Note: the shared compute module sets prevent_destroy on the instance/volume
# for the PROD use. For ephemeral teardown, destruction is performed against
# THIS root's isolated state via the gated teardown with the env tag check;
# treat any prevent_destroy friction here as a signal to use the documented
# stage-teardown path, never to weaken the shared module.

module "stage" {
  source              = "../modules/compute"
  region              = var.region
  instance_type       = var.instance_type
  label               = "arxii-stage-${var.run_id}"
  authorized_keys     = var.authorized_keys
  data_volume_size_gb = 20
  tags                = ["arxii", "ephemeral-stage", var.run_id]
}

output "stage_ipv4" {
  value = module.stage.ipv4
}
