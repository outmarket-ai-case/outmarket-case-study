output "host" { value = aws_db_instance.this.address }
output "port" { value = aws_db_instance.this.port }
output "database_name" { value = var.database_name }
output "username" { value = var.database_username }
output "engine_version" { value = aws_db_instance.this.engine_version }
output "security_group_id" { value = aws_security_group.db.id }

output "secret_ref" {
  description = "Secrets Manager ARN. The value itself never leaves the cloud."
  value       = aws_secretsmanager_secret.db.arn
}
