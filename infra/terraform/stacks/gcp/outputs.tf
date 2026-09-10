# `platform` is the only output downstream tooling is allowed to read.
output "platform" {
  description = "Cloud-neutral environment contract consumed by Helm, the CD pipeline and the AI gate."
  value       = module.platform.platform
}

# Convenience passthroughs for humans debugging a deploy.
output "kubeconfig_command" { value = module.kubernetes.kubeconfig_command }
output "namespace" { value = local.namespace }
output "network_name" { value = module.network.network_name }
