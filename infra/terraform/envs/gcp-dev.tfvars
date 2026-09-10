# GCP / dev -- same intent as aws-dev.tfvars.
environment = "dev"
region      = "europe-west1"
project_id  = "REPLACE_WITH_YOUR_GCP_PROJECT"

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
