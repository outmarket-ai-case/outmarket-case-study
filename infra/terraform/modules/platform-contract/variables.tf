variable "cloud" {
  description = "Provider slug. Extend the allowed list when onboarding a new cloud."
  type        = string
  validation {
    condition     = contains(["aws", "gcp", "azure"], var.cloud)
    error_message = "cloud must be one of: aws, gcp, azure."
  }
}

variable "environment" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,20}$", var.environment))
    error_message = "environment must be lowercase alphanumeric with dashes (<=21 chars)."
  }
}

variable "region" {
  type = string
}

variable "account_id" {
  description = <<-EOT
    The provider's account scope: an AWS account id, a GCP project id, an Azure
    subscription id. Generalising this rather than naming it `project_id` is
    what keeps the contract from leaking GCP vocabulary downstream.
  EOT
  type        = string
}

variable "cluster" {
  description = "Normalised Kubernetes facts."
  type = object({
    name               = string
    endpoint           = string
    kubeconfig_command = string # exact CLI call that writes a kubeconfig
    ingress_class      = string # nginx | alb | gce -- selected by the Helm chart
    storage_class      = string
    node_count         = number
  })
  validation {
    condition     = var.cluster.name != "" && var.cluster.kubeconfig_command != ""
    error_message = "cluster.name and cluster.kubeconfig_command are required by the CD pipeline."
  }
}

variable "registry" {
  description = "Container registry the pipeline pushes to."
  type = object({
    host              = string # e.g. 1234.dkr.ecr.eu-west-1.amazonaws.com
    repository_prefix = string # images land at <host>/<prefix>/<component>
    login_command     = string
  })
  validation {
    condition     = var.registry.host != "" && var.registry.login_command != ""
    error_message = "registry.host and registry.login_command are required by the build stage."
  }
}

variable "database" {
  description = <<-EOT
    Managed Postgres facts. The password is never an output: only a reference to
    the cloud secret store (`secret_ref`) crosses this boundary, and the
    in-cluster External Secret resolves it at deploy time.
  EOT
  type = object({
    host           = string
    port           = number
    name           = string
    username       = string
    engine_version = string
    secret_ref     = string # ARN / resource name of the password secret
    secret_backend = string # secretsmanager | secretmanager | keyvault
  })
  validation {
    condition     = var.database.port > 0 && var.database.secret_ref != ""
    error_message = "database.port and database.secret_ref are required."
  }
  validation {
    condition     = startswith(var.database.engine_version, "16")
    error_message = "all clouds must run the same Postgres major (16) so behaviour is identical."
  }
}

variable "service_account_annotations" {
  description = <<-EOT
    The one genuinely cloud-shaped detail left in the contract: the annotations
    that bind a Kubernetes ServiceAccount to a cloud identity (IRSA on AWS,
    Workload Identity on GCP). Passed straight through to the Helm chart, so the
    chart stays provider-blind.
  EOT
  type        = map(string)
  default     = {}
}

variable "app_hostname" {
  description = "Public hostname (or the LB address when no DNS zone is managed)."
  type        = string
  default     = ""
}
