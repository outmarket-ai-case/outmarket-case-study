# GCP root module. Structurally identical to stacks/aws/main.tf: same three
# role modules, same workload-identity grant, same platform contract out.

# Enabling APIs is a GCP-specific bootstrap step with no AWS counterpart.
resource "google_project_service" "required" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "sqladmin.googleapis.com",
    "servicenetworking.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "iamcredentials.googleapis.com",
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

module "network" {
  source = "../../modules/gcp-network"

  name_prefix = var.name_prefix
  environment = var.environment
  region      = var.region
  vpc_cidr    = var.vpc_cidr

  depends_on = [google_project_service.required]
}

module "kubernetes" {
  source = "../../modules/gcp-kubernetes"

  name_prefix = var.name_prefix
  environment = var.environment
  project_id  = var.project_id
  region      = var.region

  network_id          = module.network.network_id
  subnet_id           = module.network.subnet_id
  pods_range_name     = module.network.pods_range_name
  services_range_name = module.network.services_range_name
  node_tag            = module.network.node_tag

  node_machine_type          = local.node_machine_type
  node_capacity_type         = local.use_spot ? "SPOT" : "ON_DEMAND"
  node_desired_size_per_zone = local.nodes_per_zone
  node_min_size_per_zone     = local.nodes_per_zone_min
  node_max_size_per_zone     = local.nodes_per_zone_max

  authorized_networks = var.api_authorized_networks
  deletion_protection = var.deletion_protection
}

module "database" {
  source = "../../modules/gcp-database"

  name_prefix = var.name_prefix
  environment = var.environment
  project_id  = var.project_id
  region      = var.region
  network_id  = module.network.network_id

  private_service_access_connection = module.network.private_service_access_connection

  instance_tier         = local.db_instance_tier
  allocated_storage     = local.db_allocated
  max_allocated_storage = local.db_allocated * 5
  multi_az              = var.high_availability
  backup_retention_days = var.backup_retention_days
  deletion_protection   = var.deletion_protection
  performance_insights  = var.high_availability

  labels = local.common_labels
}

# --- workload identity -------------------------------------------------------
# GCP's answer to IRSA: a Google service account the Kubernetes SA impersonates.
# Same outcome as AWS -- the pod reads its own secret, no static keys anywhere.
resource "google_service_account" "app" {
  account_id   = substr("${var.name_prefix}-${var.environment}-app", 0, 30)
  project      = var.project_id
  display_name = "Workload identity for ${var.name_prefix}/${var.environment}"
}

resource "google_secret_manager_secret_iam_member" "app_read_db_secret" {
  secret_id = module.database.secret_ref
  project   = var.project_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app.email}"
}

resource "google_service_account_iam_member" "app_workload_identity" {
  service_account_id = google_service_account.app.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${local.namespace}/${var.app_service_account}]"
}

# --- the contract ------------------------------------------------------------
module "platform" {
  source = "../../modules/platform-contract"

  cloud       = "gcp"
  environment = var.environment
  region      = var.region
  account_id  = var.project_id

  cluster = {
    name               = module.kubernetes.cluster_name
    endpoint           = module.kubernetes.cluster_endpoint
    kubeconfig_command = module.kubernetes.kubeconfig_command
    ingress_class      = "gce"
    storage_class      = "standard-rwo"
    node_count         = module.kubernetes.node_count
  }

  registry = {
    host              = module.kubernetes.registry_host
    repository_prefix = module.kubernetes.registry_repository_prefix
    login_command     = module.kubernetes.registry_login_command
  }

  database = {
    host           = module.database.host
    port           = module.database.port
    name           = module.database.database_name
    username       = module.database.username
    engine_version = module.database.engine_version
    secret_ref     = module.database.secret_ref
    secret_backend = "secretmanager"
  }

  service_account_annotations = {
    "iam.gke.io/gcp-service-account" = google_service_account.app.email
  }

  app_hostname = var.app_hostname
}
