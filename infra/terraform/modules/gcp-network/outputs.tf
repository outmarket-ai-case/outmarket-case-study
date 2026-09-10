output "network_id" { value = google_compute_network.this.id }
output "network_name" { value = google_compute_network.this.name }
output "subnet_id" { value = google_compute_subnetwork.nodes.id }
output "subnet_name" { value = google_compute_subnetwork.nodes.name }
output "pods_range_name" { value = "pods" }
output "services_range_name" { value = "services" }
output "node_tag" { value = "${var.name_prefix}-${var.environment}-node" }

output "private_service_access_connection" {
  description = "Depend on this before creating Cloud SQL with a private IP."
  value       = google_service_networking_connection.private_service_access.id
}
