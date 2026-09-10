# AWS / prod -- high availability. Multi-AZ RDS, NAT per AZ, on-demand nodes.
environment = "prod"
region      = "eu-west-1"

node_size      = "medium"
db_size        = "medium"
node_count     = 3
node_min_count = 3
node_max_count = 9
az_count       = 3

high_availability     = true
cost_optimized        = false
deletion_protection   = true
backup_retention_days = 14

vpc_cidr = "10.30.0.0/16"

# Narrow this to your CI egress + operator ranges before going live.
api_authorized_networks = ["0.0.0.0/0"]
