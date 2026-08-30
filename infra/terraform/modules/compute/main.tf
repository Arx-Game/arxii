# Prod host + a persistent data volume.
#
# prevent_destroy on BOTH (per the plan's stateful set): the volume holds
# Postgres data / backup staging; the instance is the live host. A change to
# a ForceNew attribute (region/image/type) therefore HARD-FAILS the apply
# rather than silently replacing — fail-closed, manual intervention required.
# That is the intended "the button never obliterates prod" behaviour.
#
# Provider-schema caveat: `linode_instance` / `linode_volume` argument names
# have shifted across provider majors (e.g. authorized_keys placement, the
# instance-config/disk model). Written for ~> 2.20; CI `tofu validate`
# against the pinned provider is the authority — fix there, do not guess.

resource "linode_instance" "host" {
  region          = var.region
  type            = var.instance_type
  image           = var.image
  label           = var.label
  tags            = var.tags
  authorized_keys = var.authorized_keys

  lifecycle {
    prevent_destroy = true
    # authorized_keys is a create-time-only attribute (ForceNew): editing the
    # ARXII_AUTHORIZED_KEYS variable would otherwise plan a full instance
    # replacement, which prevent_destroy then hard-fails (2026-08-30: adding a
    # second admin key bricked the button this way). Post-boot key management
    # belongs to the base role's authorized_key task, which reads the same
    # tofu output on every converge — cloud-init only needs the key list that
    # existed at first boot.
    ignore_changes = [authorized_keys]
  }
}

resource "linode_volume" "data" {
  region    = var.region
  label     = "${var.label}-data"
  size      = var.data_volume_size_gb
  linode_id = linode_instance.host.id
  tags      = var.tags

  lifecycle {
    prevent_destroy = true
  }
}
