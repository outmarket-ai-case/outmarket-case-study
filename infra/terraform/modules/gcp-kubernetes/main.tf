# GCP implementation of the `kubernetes` role: a regional VPC-native GKE
# cluster with Workload Identity (the GCP analogue of IRSA) + Artifact Registry.
terraform {
  required_version = ">= 1.6"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.14" }
  }
}

locals {
  cluster_name = "${var.name_prefix}-${var.environment}"
}

# Least-privilege node identity: the default compute SA is far too broad.
resource "google_service_account" "node" {
  account_id   = substr("${local.cluster_name}-node", 0, 30)
  display_name = "GKE nodes for ${local.cluster_name}"
}

resource "google_project_iam_member" "node" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/artifactregistry.reader",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.node.email}"
}

resource "google_container_cluster" "this" {
  name     = local.cluster_name
  location = var.region # regional => control plane spread across zones
  project  = var.project_id

  # We manage the node pool separately so its lifecycle is independent.
  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = var.deletion_protection

  min_master_version = var.kubernetes_version
  network            = var.network_id
  subnetwork         = var.subnet_id
  networking_mode    = "VPC_NATIVE"

  ip_allocation_policy {
    cluster_secondary_range_name  = var.pods_range_name
    services_secondary_range_name = var.services_range_name
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_cidr
  }

  master_authorized_networks_config {
    dynamic "cidr_blocks" {
      for_each = var.authorized_networks
      content {
        cidr_block   = cidr_blocks.value
        display_name = "authorized-${cidr_blocks.key}"
      }
    }
  }

  # Pods assume GCP identities via KSA annotations -- no key files on disk.
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  release_channel {
    channel = var.release_channel
  }

  addons_config {
    http_load_balancing { disabled = false }
    horizontal_pod_autoscaling { disabled = false }
  }

  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus { enabled = true }
  }

  lifecycle {
    ignore_changes = [initial_node_count]
  }
}

resource "google_container_node_pool" "default" {
  name     = "${local.cluster_name}-default"
  cluster  = google_container_cluster.this.id
  location = var.region

  initial_node_count = var.node_desired_size_per_zone

  autoscaling {
    min_node_count = var.node_min_size_per_zone
    max_node_count = var.node_max_size_per_zone
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }

  node_config {
    machine_type = var.node_machine_type
    disk_size_gb = var.node_disk_size
    disk_type    = "pd-balanced"
    spot         = var.node_capacity_type == "SPOT"

    service_account = google_service_account.node.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    labels = { workload = "general" }
    tags   = [var.node_tag]

    # Blocks the legacy metadata endpoints that leak node credentials to pods.
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }

  lifecycle {
    ignore_changes = [initial_node_count]
  }
}

# --- container registry ------------------------------------------------------
resource "google_artifact_registry_repository" "this" {
  location      = var.region
  repository_id = var.name_prefix
  format        = "DOCKER"
  description   = "Images for ${local.cluster_name}"

  docker_config {
    immutable_tags = true
  }

  cleanup_policies {
    id     = "expire-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s" # 7 days
    }
  }
}
