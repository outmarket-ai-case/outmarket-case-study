variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "region" { type = string }

variable "private_subnet_ids" { type = list(string) }
variable "public_subnet_ids" { type = list(string) }

variable "kubernetes_version" {
  type    = string
  default = "1.31"
}

variable "endpoint_public_access" {
  type    = bool
  default = true
}

variable "public_access_cidrs" {
  description = "Who may reach the API server. Narrow this to your CI + office ranges."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "node_instance_types" { type = list(string) }
variable "node_capacity_type" {
  type    = string
  default = "ON_DEMAND"
  validation {
    condition     = contains(["ON_DEMAND", "SPOT"], var.node_capacity_type)
    error_message = "node_capacity_type must be ON_DEMAND or SPOT."
  }
}
variable "node_desired_size" { type = number }
variable "node_min_size" { type = number }
variable "node_max_size" { type = number }
variable "node_disk_size" {
  type    = number
  default = 40
}

variable "image_repositories" {
  type    = list(string)
  default = ["frontend", "backend"]
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
