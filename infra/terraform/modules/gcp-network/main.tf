# GCP implementation of the `network` role. Same responsibilities as
# aws-network: private workload subnets, egress NAT, and a private path to the
# managed database (here: a Private Service Access peering for Cloud SQL).
terraform {
  required_version = ">= 1.6"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.14" }
  }
}

locals {
  name = "${var.name_prefix}-${var.environment}"
}

resource "google_compute_network" "this" {
  name                    = local.name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "nodes" {
  name          = "${local.name}-nodes"
  network       = google_compute_network.this.id
  region        = var.region
  ip_cidr_range = cidrsubnet(var.vpc_cidr, 4, 0)

  # VPC-native GKE: pods and services get their own alias ranges instead of
  # route-based networking.
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = cidrsubnet(var.vpc_cidr, 2, 1)
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = cidrsubnet(var.vpc_cidr, 6, 2)
  }

  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# Egress for private nodes -- the GCP counterpart of the NAT gateways.
resource "google_compute_router" "this" {
  name    = "${local.name}-router"
  network = google_compute_network.this.id
  region  = var.region
}

resource "google_compute_router_nat" "this" {
  name                               = "${local.name}-nat"
  router                             = google_compute_router.this.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = var.enable_flow_logs
    filter = "ERRORS_ONLY"
  }
}

# --- private path to Cloud SQL ----------------------------------------------
resource "google_compute_global_address" "private_service_access" {
  name          = "${local.name}-psa"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.this.id
}

resource "google_service_networking_connection" "private_service_access" {
  network                 = google_compute_network.this.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_access.name]
}

# --- firewall ----------------------------------------------------------------
# GCP denies ingress by default, so only the rules we actually need exist.
resource "google_compute_firewall" "allow_internal" {
  name      = "${local.name}-allow-internal"
  network   = google_compute_network.this.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = [
    google_compute_subnetwork.nodes.ip_cidr_range,
    cidrsubnet(var.vpc_cidr, 2, 1), # pods
  ]

  allow {
    protocol = "tcp"
  }
  allow {
    protocol = "udp"
  }
  allow {
    protocol = "icmp"
  }
}

# Health-check + LB probe ranges must reach node ports for Ingress to work.
resource "google_compute_firewall" "allow_health_checks" {
  name          = "${local.name}-allow-health-checks"
  network       = google_compute_network.this.name
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["35.191.0.0/16", "130.211.0.0/22"]
  target_tags   = ["${local.name}-node"]

  allow {
    protocol = "tcp"
  }
}
