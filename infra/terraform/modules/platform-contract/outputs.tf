output "platform" {
  description = "The cloud-neutral environment contract. The only thing downstream tooling reads."
  value = {
    schema_version = "1.0"
    cloud          = var.cloud
    environment    = var.environment
    region         = var.region
    account_id     = var.account_id

    cluster  = var.cluster
    registry = var.registry

    database = merge(var.database, {
      connection_url_template = local.connection_url_template
    })

    service_account_annotations = var.service_account_annotations
    app_hostname                = var.app_hostname
  }
}
