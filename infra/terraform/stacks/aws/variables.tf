# ---------------------------------------------------------------------------
# THE CLOUD-NEUTRAL VARIABLE CONTRACT
#
# Every variable below (except `aws_*`) exists with the same name, type and
# meaning in stacks/gcp. Switching clouds means changing `region` and pointing
# at the other tfvars file -- the sizing, topology and HA intent carry over
# verbatim. See docs/cloud-agnostic.md.
# ---------------------------------------------------------------------------

variable "name_prefix" {
  description = "Short slug prefixed to every resource name."
  type        = string
  default     = "idea-board"
}

variable "environment" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,20}$", var.environment))
    error_message = "environment must be lowercase alphanumeric with dashes."
  }
}

variable "region" {
  description = "Provider region. The ONLY variable whose value is cloud-shaped."
  type        = string
}

# --- capacity, expressed as cloud-neutral t-shirt sizes ---------------------
variable "node_size" {
  description = "Translated to a concrete machine type in sizing.tf."
  type        = string
  default     = "small"
  validation {
    condition     = contains(["small", "medium", "large"], var.node_size)
    error_message = "node_size must be small, medium or large."
  }
}

variable "db_size" {
  type    = string
  default = "small"
  validation {
    condition     = contains(["small", "medium", "large"], var.db_size)
    error_message = "db_size must be small, medium or large."
  }
}

variable "node_count" {
  description = "Desired worker nodes for the whole cluster."
  type        = number
  default     = 2
  validation {
    condition     = var.node_count >= 1
    error_message = "node_count must be at least 1."
  }
}

variable "node_min_count" {
  type    = number
  default = 1
}

variable "node_max_count" {
  type    = number
  default = 4
}

variable "az_count" {
  type    = number
  default = 2
}

# --- intent flags: the AI env-spec compiler writes exactly these ------------
variable "high_availability" {
  description = "Multi-AZ database, NAT per AZ, no spot capacity."
  type        = bool
  default     = false
}

variable "cost_optimized" {
  description = "Spot workers and a single shared NAT. Mutually exclusive with HA."
  type        = bool
  default     = true
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "backup_retention_days" {
  type    = number
  default = 7
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "api_authorized_networks" {
  description = "CIDRs allowed to reach the Kubernetes API server."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "app_namespace" {
  description = "Kubernetes namespace the workload lands in."
  type        = string
  default     = ""
}

variable "app_service_account" {
  type    = string
  default = "idea-board"
}

variable "app_hostname" {
  description = "Public hostname. Empty means 'use the load balancer address'."
  type        = string
  default     = ""
}

variable "extra_tags" {
  type    = map(string)
  default = {}
}
