output "host" { value = google_sql_database_instance.this.private_ip_address }
output "port" { value = 5432 }
output "database_name" { value = google_sql_database.this.name }
output "username" { value = google_sql_user.app.name }
output "engine_version" { value = var.engine_version }
output "instance_connection_name" { value = google_sql_database_instance.this.connection_name }

output "secret_ref" {
  description = "Secret Manager resource name. The value itself never leaves the cloud."
  value       = google_secret_manager_secret.db.id
}
