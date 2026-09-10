variable "name_prefix" { type = string }
variable "environment" { type = string }

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
  validation {
    condition     = can(cidrsubnet(var.vpc_cidr, 4, 0))
    error_message = "vpc_cidr must be a valid CIDR with room for /20 subnets (i.e. /16 or larger)."
  }
}

variable "az_count" {
  type    = number
  default = 3
  validation {
    condition     = var.az_count >= 2 && var.az_count <= 4
    error_message = "az_count must be between 2 and 4; managed Postgres and EKS both need >= 2."
  }
}

variable "single_nat_gateway" {
  description = "true saves ~2x NAT cost but makes one AZ a SPOF. Never true for prod."
  type        = bool
  default     = false
}

variable "enable_flow_logs" {
  type    = bool
  default = true
}

variable "flow_log_retention_days" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
