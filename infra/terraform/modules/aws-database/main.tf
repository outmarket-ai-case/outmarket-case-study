# AWS implementation of the `database` role: RDS Postgres, private-only, with
# the generated password stored in Secrets Manager. The password is never an
# output of this module -- only `secret_ref` crosses the boundary.
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.80" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

locals {
  identifier = "${var.name_prefix}-${var.environment}"
}

resource "random_password" "db" {
  length  = 32
  special = true
  # RDS rejects these in master passwords.
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_db_subnet_group" "this" {
  name       = "${local.identifier}-db"
  subnet_ids = var.private_subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "db" {
  name        = "${local.identifier}-db"
  description = "Postgres access for ${local.identifier}"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${local.identifier}-db" })
}

# Only the cluster's node security group may reach 5432 -- no CIDR-wide rules.
resource "aws_vpc_security_group_ingress_rule" "from_cluster" {
  security_group_id            = aws_security_group.db.id
  description                  = "Postgres from EKS nodes"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  referenced_security_group_id = var.client_security_group_id
}

resource "aws_kms_key" "db" {
  description             = "RDS storage encryption for ${local.identifier}"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  tags                    = var.tags
}

resource "aws_db_parameter_group" "this" {
  name   = "${local.identifier}-pg16"
  family = "postgres16"

  parameter {
    name  = "log_min_duration_statement"
    value = "500"
  }
  # TLS is mandatory: the driver connects with sslmode=require.
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "this" {
  identifier     = local.identifier
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.db.arn

  db_name  = var.database_name
  username = var.database_username
  password = random_password.db.result
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false

  multi_az                = var.multi_az
  backup_retention_period = var.backup_retention_days
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:30-sun:05:30"
  parameter_group_name    = aws_db_parameter_group.this.name

  auto_minor_version_upgrade      = true
  performance_insights_enabled    = var.performance_insights
  enabled_cloudwatch_logs_exports = ["postgresql"]

  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = !var.deletion_protection
  final_snapshot_identifier = var.deletion_protection ? "${local.identifier}-final" : null
  apply_immediately         = var.environment != "prod"

  tags = merge(var.tags, { Name = local.identifier })
}

resource "aws_secretsmanager_secret" "db" {
  name                    = "${local.identifier}/database"
  description             = "Postgres credentials for ${local.identifier}"
  recovery_window_in_days = var.environment == "prod" ? 30 : 0
  tags                    = var.tags
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  # Shape matches the GCP secret exactly, so the External Secret template that
  # renders DATABASE_URL is identical on both clouds.
  secret_string = jsonencode({
    username = var.database_username
    password = random_password.db.result
    host     = aws_db_instance.this.address
    port     = aws_db_instance.this.port
    dbname   = var.database_name
  })
}
