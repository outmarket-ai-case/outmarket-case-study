variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }

variable "client_security_group_id" {
  description = "Security group allowed to reach Postgres (the EKS cluster SG)."
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

variable "instance_class" { type = string }
variable "allocated_storage" {
  type    = number
  default = 20
}
variable "max_allocated_storage" {
  description = "Storage autoscaling ceiling; 0 disables it."
  type        = number
  default     = 100
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

variable "tags" {
  type    = map(string)
  default = {}
}
