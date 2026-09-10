# platform-contract

The single source of truth for what "a deployed environment" means, independent
of cloud. Every cloud stack (`stacks/aws`, `stacks/gcp`, ...) feeds its
provider-specific resource attributes into this module, and the module emits one
normalised `platform` object.

Everything downstream -- the Helm chart, the AI release gate, the CI/CD
pipeline -- consumes **only** this object. That is what makes the delivery layer
cloud-agnostic: it has no idea whether it is talking to EKS or GKE.

Adding a third cloud means implementing three modules (`network`, `kubernetes`,
`database`) and wiring their outputs into this contract. Nothing downstream
changes. The variable validations below are what stop a new provider from
quietly emitting a half-populated contract.
