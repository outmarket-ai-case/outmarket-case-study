variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "project_id" { type = string }
variable "region" { type = string }

variable "network_id" { type = string }
variable "subnet_id" { type = string }
variable "pods_range_name" { type = string }
variable "services_range_name" { type = string }
variable "node_tag" { type = string }

variable "master_cidr" {
  description = "Reserved /28 for the GKE control plane; must not overlap the VPC."
  type        = string
  default     = "172.16.0.0/28"
}

variable "authorized_networks" {
  description = "Who may reach the API server. Narrow this to your CI + office ranges."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "kubernetes_version" {
  type    = string
  default = "1.31"
}

variable "release_channel" {
  type    = string
  default = "REGULAR"
  validation {
    condition     = contains(["RAPID", "REGULAR", "STABLE"], var.release_channel)
    error_message = "release_channel must be RAPID, REGULAR or STABLE."
  }
}

variable "node_machine_type" { type = string }
variable "node_capacity_type" {
  type    = string
  default = "ON_DEMAND"
}
variable "node_desired_size_per_zone" { type = number }
variable "node_min_size_per_zone" { type = number }
variable "node_max_size_per_zone" { type = number }
variable "node_disk_size" {
  type    = number
  default = 40
}

variable "deletion_protection" {
  type    = bool
  default = false
}
