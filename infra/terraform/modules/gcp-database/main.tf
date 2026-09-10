# GCP implementation of the `database` role: Cloud SQL for Postgres on a
# private IP, password held in Secret Manager. Mirrors aws-database exactly --
# same inputs, same output names, same secret JSON shape.
terraform {
  required_version = ">= 1.6"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.14" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

locals {
  instance_name = "${var.name_prefix}-${var.environment}"
}

resource "random_password" "db" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "google_sql_database_instance" "this" {
  name             = local.instance_name
  project          = var.project_id
  region           = var.region
  database_version = "POSTGRES_${split(".", var.engine_version)[0]}"

  deletion_protection = var.deletion_protection

  settings {
    tier                  = var.instance_tier
    availability_type     = var.multi_az ? "REGIONAL" : "ZONAL"
    disk_size             = var.allocated_storage
    disk_type             = "PD_SSD"
    disk_autoresize       = var.max_allocated_storage > var.allocated_storage
    disk_autoresize_limit = var.max_allocated_storage

    ip_configuration {
      # No public IP at all; reachable only over the VPC peering.
      ipv4_enabled                                  = false
      private_network                               = var.network_id
      enable_private_path_for_google_cloud_services = true
      ssl_mode                                      = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = var.multi_az
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = var.backup_retention_days
        retention_unit   = "COUNT"
      }
    }

    maintenance_window {
      day  = 7 # Sunday
      hour = 4
    }

    database_flags {
      name  = "log_min_duration_statement"
      value = "500"
    }

    insights_config {
      query_insights_enabled = var.performance_insights
    }

    user_labels = var.labels
  }

  # Cloud SQL cannot get a private IP before the PSA peering exists.
  depends_on = [var.private_service_access_connection]
}

resource "google_sql_database" "this" {
  name     = var.database_name
  project  = var.project_id
  instance = google_sql_database_instance.this.name
}

resource "google_sql_user" "app" {
  name     = var.database_username
  project  = var.project_id
  instance = google_sql_database_instance.this.name
  password = random_password.db.result
}

resource "google_secret_manager_secret" "db" {
  secret_id = "${local.instance_name}-database"
  project   = var.project_id
  labels    = var.labels

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db" {
  secret = google_secret_manager_secret.db.id
  # Identical JSON shape to the AWS secret -- that is what lets one Helm
  # template render DATABASE_URL on either cloud.
  secret_data = jsonencode({
    username = var.database_username
    password = random_password.db.result
    host     = google_sql_database_instance.this.private_ip_address
    port     = 5432
    dbname   = var.database_name
  })
}
