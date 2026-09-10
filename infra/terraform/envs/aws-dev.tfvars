# AWS / dev -- cost-sensitive. Compare against gcp-dev.tfvars: only `region`
# and the GCP-only `project_id` differ.
environment = "dev"
region      = "eu-west-1"

node_size      = "small"
db_size        = "small"
node_count     = 2
node_min_count = 1
node_max_count = 4
az_count       = 2

high_availability     = false
cost_optimized        = true
deletion_protection   = false
backup_retention_days = 3

vpc_cidr = "10.20.0.0/16"
