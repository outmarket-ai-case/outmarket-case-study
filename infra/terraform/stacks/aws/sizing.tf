# The whole cloud-specific vocabulary of this stack lives in this one file.
# A cloud-neutral t-shirt size in, an AWS instance type out. stacks/gcp has the
# identical file with GCP machine types -- that is the seam a third cloud slots
# into.
locals {
  node_machine_types = {
    small  = ["t3.medium"]  # 2 vCPU / 4 GiB
    medium = ["m6i.large"]  # 2 vCPU / 8 GiB
    large  = ["m6i.xlarge"] # 4 vCPU / 16 GiB
  }

  db_instance_classes = {
    small  = "db.t4g.micro"
    medium = "db.t4g.medium"
    large  = "db.m6g.large"
  }

  db_storage_gb = {
    small  = 20
    medium = 50
    large  = 100
  }

  node_instance_types = local.node_machine_types[var.node_size]
  db_instance_class   = local.db_instance_classes[var.db_size]
  db_allocated        = local.db_storage_gb[var.db_size]

  # HA always wins over cost optimisation if both are somehow set.
  use_spot           = var.cost_optimized && !var.high_availability
  single_nat         = var.cost_optimized && !var.high_availability
  effective_az_count = var.high_availability ? max(var.az_count, 3) : var.az_count

  namespace = var.app_namespace != "" ? var.app_namespace : "${var.name_prefix}-${var.environment}"

  common_tags = merge({
    Application = var.name_prefix
    Environment = var.environment
    ManagedBy   = "terraform"
    Stack       = "aws"
  }, var.extra_tags)
}
