# Mirror of stacks/aws/sizing.tf. Same t-shirt sizes in, GCP machine types out.
# Sizes are matched on vCPU/RAM so a "medium" environment behaves the same on
# either cloud -- otherwise "cloud-agnostic" would only be true on paper.
locals {
  node_machine_types = {
    small  = "e2-medium"     # 2 vCPU / 4 GiB   ~ t3.medium
    medium = "e2-standard-2" # 2 vCPU / 8 GiB   ~ m6i.large
    large  = "e2-standard-4" # 4 vCPU / 16 GiB  ~ m6i.xlarge
  }

  db_instance_tiers = {
    small  = "db-f1-micro"
    medium = "db-custom-2-4096"
    large  = "db-custom-2-8192"
  }

  db_storage_gb = {
    small  = 20
    medium = 50
    large  = 100
  }

  node_machine_type = local.node_machine_types[var.node_size]
  db_instance_tier  = local.db_instance_tiers[var.db_size]
  db_allocated      = local.db_storage_gb[var.db_size]

  use_spot = var.cost_optimized && !var.high_availability

  # GKE regional node pools count per zone (3 zones), so convert the
  # contract's cluster-wide counts into per-zone counts.
  nodes_per_zone     = max(1, ceil(var.node_count / 3))
  nodes_per_zone_min = max(1, ceil(var.node_min_count / 3))
  nodes_per_zone_max = max(local.nodes_per_zone, ceil(var.node_max_count / 3))

  namespace = var.app_namespace != "" ? var.app_namespace : "${var.name_prefix}-${var.environment}"

  common_labels = merge({
    application = var.name_prefix
    environment = var.environment
    managed_by  = "terraform"
    stack       = "gcp"
  }, var.extra_tags)
}
