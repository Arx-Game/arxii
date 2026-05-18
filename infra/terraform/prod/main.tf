# Prod composition. The full prevent_destroy set lives inside the modules
# (compute instance+volume, object_storage backups bucket, r2 offsite bucket,
# cloudflare zone; state bucket lives in bootstrap). This root only wires
# them. apply-only — the button never runs destroy.

# Cloudflare published IP ranges via the provider data source (no hand-
# maintained CIDR list). v4 idiom; CI confirms the data-source shape.
data "cloudflare_ip_ranges" "cf" {}

module "compute" {
  source              = "../modules/compute"
  region              = var.region
  instance_type       = var.instance_type
  label               = var.instance_label
  authorized_keys     = var.authorized_keys
  data_volume_size_gb = 40
}

module "firewall" {
  source                = "../modules/linode_firewall"
  label                 = "${var.instance_label}-fw"
  linode_id             = module.compute.instance_id
  ssh_admin_cidrs       = var.ssh_admin_cidrs
  cloudflare_ipv4_cidrs = data.cloudflare_ip_ranges.cf.ipv4_cidr_blocks
  cloudflare_ipv6_cidrs = data.cloudflare_ip_ranges.cf.ipv6_cidr_blocks
  tls_telnet_port       = var.tls_telnet_port
}

module "dns" {
  source             = "../modules/cloudflare_dns"
  account_id         = var.cloudflare_account_id
  domain             = var.domain
  web_hostname       = var.web_hostname
  telnet_hostname    = var.telnet_hostname
  origin_ipv4        = module.compute.ipv4
  origin_ipv6        = module.compute.ipv6
  dmarc_policy       = var.dmarc_policy
  dmarc_rua          = var.dmarc_rua
  resend_spf_include = var.resend_spf_include
  resend_records     = var.resend_records
}

module "object_storage" {
  source                     = "../modules/object_storage"
  region                     = var.region
  label                      = var.state_bucket_label
  object_lock_retention_days = 30
}

module "r2_offsite" {
  source                     = "../modules/r2_offsite"
  account_id                 = var.cloudflare_account_id
  bucket_name                = var.r2_bucket_name
  object_lock_retention_days = 30
}
