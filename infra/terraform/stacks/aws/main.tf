# AWS root module. Composes the three role modules, grants the workload a
# least-privilege identity, and publishes the cloud-neutral platform contract.

module "network" {
  source = "../../modules/aws-network"

  name_prefix        = var.name_prefix
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  az_count           = local.effective_az_count
  single_nat_gateway = local.single_nat
  tags               = local.common_tags
}

module "kubernetes" {
  source = "../../modules/aws-kubernetes"

  name_prefix        = var.name_prefix
  environment        = var.environment
  region             = var.region
  private_subnet_ids = module.network.private_subnet_ids
  public_subnet_ids  = module.network.public_subnet_ids

  node_instance_types = local.node_instance_types
  node_capacity_type  = local.use_spot ? "SPOT" : "ON_DEMAND"
  node_desired_size   = var.node_count
  node_min_size       = var.node_min_count
  node_max_size       = var.node_max_count

  public_access_cidrs = var.api_authorized_networks
  tags                = local.common_tags
}

module "database" {
  source = "../../modules/aws-database"

  name_prefix              = var.name_prefix
  environment              = var.environment
  vpc_id                   = module.network.vpc_id
  private_subnet_ids       = module.network.private_subnet_ids
  client_security_group_id = module.kubernetes.node_security_group_id

  instance_class        = local.db_instance_class
  allocated_storage     = local.db_allocated
  max_allocated_storage = local.db_allocated * 5
  multi_az              = var.high_availability
  backup_retention_days = var.backup_retention_days
  deletion_protection   = var.deletion_protection
  performance_insights  = var.high_availability

  tags = local.common_tags
}

data "aws_caller_identity" "current" {}

# --- workload identity (IRSA) ------------------------------------------------
# The pod reads its database password directly from Secrets Manager. No static
# credentials exist anywhere in the pipeline or in Terraform state.
data "aws_iam_policy_document" "app_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [module.kubernetes.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${module.kubernetes.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:${local.namespace}:${var.app_service_account}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${module.kubernetes.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "${var.name_prefix}-${var.environment}-app"
  assume_role_policy = data.aws_iam_policy_document.app_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "app_read_db_secret" {
  name = "read-db-secret"
  role = aws_iam_role.app.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      Resource = module.database.secret_ref
    }]
  })
}

# --- the contract ------------------------------------------------------------
module "platform" {
  source = "../../modules/platform-contract"

  cloud       = "aws"
  environment = var.environment
  region      = var.region
  account_id  = data.aws_caller_identity.current.account_id

  cluster = {
    name               = module.kubernetes.cluster_name
    endpoint           = module.kubernetes.cluster_endpoint
    kubeconfig_command = module.kubernetes.kubeconfig_command
    ingress_class      = "alb"
    storage_class      = "gp2"
    node_count         = module.kubernetes.node_count
  }

  registry = {
    host              = module.kubernetes.registry_host
    repository_prefix = var.name_prefix
    login_command     = module.kubernetes.registry_login_command
  }

  database = {
    host           = module.database.host
    port           = module.database.port
    name           = module.database.database_name
    username       = module.database.username
    engine_version = module.database.engine_version
    secret_ref     = module.database.secret_ref
    secret_backend = "secretsmanager"
  }

  service_account_annotations = {
    "eks.amazonaws.com/role-arn" = aws_iam_role.app.arn
  }

  app_hostname = var.app_hostname
}
