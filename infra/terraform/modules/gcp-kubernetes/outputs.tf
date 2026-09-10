output "cluster_name" { value = google_container_cluster.this.name }
output "cluster_endpoint" { value = "https://${google_container_cluster.this.endpoint}" }
output "cluster_ca_certificate" { value = google_container_cluster.this.master_auth[0].cluster_ca_certificate }
output "node_service_account_email" { value = google_service_account.node.email }
output "workload_identity_pool" { value = "${var.project_id}.svc.id.goog" }

# A regional cluster runs the pool in each of 3 zones.
output "node_count" { value = var.node_desired_size_per_zone * 3 }

output "kubeconfig_command" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.this.name} --region ${var.region} --project ${var.project_id}"
}

output "registry_host" { value = "${var.region}-docker.pkg.dev" }

output "registry_repository_prefix" {
  value = "${var.project_id}/${google_artifact_registry_repository.this.repository_id}"
}

output "registry_login_command" {
  value = "gcloud auth configure-docker ${var.region}-docker.pkg.dev --quiet"
}
