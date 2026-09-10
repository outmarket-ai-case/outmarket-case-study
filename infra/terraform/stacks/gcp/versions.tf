terraform {
  required_version = ">= 1.6"

  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.14" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }

  # Partial backend config, same as the AWS stack: CI passes -backend-config.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region

  default_labels = local.common_labels
}
