variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "region" { type = string }

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
  validation {
    condition     = can(cidrsubnet(var.vpc_cidr, 6, 0))
    error_message = "vpc_cidr must be a /16 or larger to fit the node, pod and service ranges."
  }
}

variable "enable_flow_logs" {
  type    = bool
  default = true
}
