variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "project_id" { type = string }
variable "region" { type = string }
variable "network_id" { type = string }

variable "private_service_access_connection" {
  description = "Output of gcp-network; sequences Cloud SQL after the peering."
  type        = string
}

variable "engine_version" {
  type    = string
  default = "16.4"
  validation {
    condition     = startswith(var.engine_version, "16")
    error_message = "Postgres major must be 16 to match the other clouds."
  }
}

variable "instance_tier" { type = string }
variable "allocated_storage" {
  type    = number
  default = 20
}
variable "max_allocated_storage" {
  type    = number
  default = 100
}

variable "database_name" {
  type    = string
  default = "ideas"
}
variable "database_username" {
  type    = string
  default = "ideas_app"
}

variable "multi_az" { type = bool }
variable "backup_retention_days" {
  type    = number
  default = 7
}
variable "deletion_protection" { type = bool }
variable "performance_insights" {
  type    = bool
  default = false
}

variable "labels" {
  type    = map(string)
  default = {}
}
