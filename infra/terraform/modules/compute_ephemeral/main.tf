# EPHEMERAL counterpart to ../compute (#2236 Phase 3 P1 finding, not in the
# original task spec — discovered while implementing the dress-rehearsal
# teardown trap). Exists as a SEPARATE module, not a flag on the prod one,
# for the exact same reason object_storage_ephemeral does: `prevent_destroy`
# is a literal in a `lifecycle` block and cannot be interpolated, so there is
# no way to parameterize "skip prevent_destroy in rehearsal" on ../compute.
#
# WHY THIS MODULE HAD TO EXIST (empirically verified, not theoretical):
# ephemeral-stage/main.tf used to call ../compute directly, on the belief
# (recorded in this file's prior comment) that reusing a module with
# `lifecycle { prevent_destroy = true }` was harmless for a root that's
# "meant to be destroyed." That is false — `prevent_destroy` is enforced by
# Terraform/OpenTofu against ANY `destroy` plan touching that resource,
# regardless of which root/state called the module; it is not scoped to
# "prod usage" by intent, only by convention. Verified locally with a
# throwaway `null_resource` carrying `lifecycle { prevent_destroy = true }`:
# `tofu destroy` hard-errors with "Instance cannot be destroyed" even though
# nothing about that resource was prod-specific. Left uncorrected, EVERY
# ephemeral-stage teardown (restore-rehearsal.sh's existing trap, and this
# phase's new rehearse.sh trap) would have failed to destroy the stage
# instance/volume, leaking a billed Linode on every single run. ../compute
# (the prod module) is UNTOUCHED — do NOT weaken it to make this work.
resource "linode_instance" "host" {
  region          = var.region
  type            = var.instance_type
  image           = var.image
  label           = var.label
  tags            = var.tags
  authorized_keys = var.authorized_keys

  # Deliberately NO lifecycle.prevent_destroy — see header. This resource
  # MUST be destroyable by the scripted stage teardown (restore-rehearsal.sh
  # / rehearse.sh), every run, unattended.
}

resource "linode_volume" "data" {
  region    = var.region
  label     = "${var.label}-data"
  size      = var.data_volume_size_gb
  linode_id = linode_instance.host.id
  tags      = var.tags

  # Same rationale — no prevent_destroy.
}
