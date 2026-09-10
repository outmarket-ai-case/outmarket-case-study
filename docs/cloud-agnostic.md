# The cloud-agnostic approach

## The claim, stated precisely

Deploying this stack to a second cloud changes **two lines of configuration**:

```console
$ diff infra/terraform/envs/aws-dev.tfvars infra/terraform/envs/gcp-dev.tfvars
< region      = "eu-west-1"
---
> region      = "europe-west1"
> project_id  = "REPLACE_WITH_YOUR_GCP_PROJECT"
```

Everything else — the sizing, the HA intent, the backup policy, the whole
delivery layer, the application, the images — is identical. That is not because
the two clouds are similar. It is because provider differences are confined to
one seam, on purpose.

## The seam: a platform contract

Cloud-agnostic designs usually fail in one of two ways. Either they abstract so
little that "agnostic" means "we wrote it twice", or they abstract so much that
the lowest common denominator throws away the managed services you are paying
for. This repository avoids both by abstracting **the interface, not the
implementation**.

Every cloud implements three modules — `network`, `kubernetes`, `database` —
using its own best-in-class managed services. Each stack then funnels those
provider-specific outputs into one normalised object:

```
                    ┌──────────────────────────┐
  stacks/aws  ─────▶│                          │
  (VPC, EKS, RDS,   │   modules/               │      ┌──────────────────┐
   ECR, IRSA)       │   platform-contract      │─────▶│  platform (JSON) │
                    │                          │      └────────┬─────────┘
  stacks/gcp  ─────▶│  validates + normalises  │               │
  (VPC, GKE, Cloud  │                          │               │
   SQL, AR, WI)     └──────────────────────────┘               │
                                                               ▼
                                        ┌──────────────────────────────────────┐
                                        │  Everything downstream reads ONLY    │
                                        │  this object:                        │
                                        │    • Helm chart (deploy/helm)        │
                                        │    • deploy script (scripts/)        │
                                        │    • AI release gate (ai/aiops)      │
                                        │    • CI/CD (.github/workflows)       │
                                        └──────────────────────────────────────┘
```

The contract ([`modules/platform-contract`](../infra/terraform/modules/platform-contract/)):

| Field | Meaning | AWS | GCP |
|---|---|---|---|
| `cluster.kubeconfig_command` | Exact CLI call that writes a kubeconfig | `aws eks update-kubeconfig …` | `gcloud container clusters get-credentials …` |
| `cluster.ingress_class` | Which ingress controller to target | `alb` | `gce` |
| `cluster.storage_class` | Default block storage class | `gp2` | `standard-rwo` |
| `registry.host` / `login_command` | Where images go and how to authenticate | ECR | Artifact Registry |
| `database.host/port/name/username` | Connection facts | RDS | Cloud SQL |
| `database.secret_ref` | **Reference** to the password, never the value | Secrets Manager ARN | Secret Manager resource name |
| `service_account_annotations` | Binds a K8s SA to a cloud identity | `eks.amazonaws.com/role-arn` | `iam.gke.io/gcp-service-account` |
| `account_id` | Account / project / subscription scope | AWS account id | GCP project id |

Two design details carry most of the weight:

**Cloud-specific commands are passed as opaque strings.** The pipeline does not
branch on the provider to authenticate — it reads `kubeconfig_command` from the
contract and executes it. Look at [`scripts/deploy.sh`](../scripts/deploy.sh):
there is no `if aws … elif gcp …` anywhere in it.

**`service_account_annotations` is a passthrough map.** Workload identity is the
one place where the two clouds genuinely disagree in shape, so rather than
pretend otherwise, the contract carries an opaque annotation map straight
through to the ServiceAccount. The chart applies it without knowing what it
means. That single design choice is why the chart needs no provider
conditionals for pod identity.

## Why not one Terraform root with a `cloud` variable?

The obvious approach — `count = var.cloud == "aws" ? 1 : 0` on every module — is
a trap, and rejecting it is a deliberate decision:

- Terraform requires every declared provider to be *configured* even when its
  resources are counted out, so a GCP deploy would still need AWS credentials.
- `terraform plan` output becomes unreadable: half the plan is resources being
  ignored.
- One state file ends up holding two clouds' resources, so a mistake in the AWS
  path can taint GCP state.

Instead: **thin per-cloud roots over shared role modules, unified by the
contract.** Each root is small (~130 lines of composition), owns its own state,
and needs only its own credentials. The *variable names* are identical across
roots, which is what makes the tfvars files interchangeable.

## Cloud-neutral sizing: t-shirt sizes

The variable contract never names a machine type. It takes `node_size = "small"`,
and each stack has exactly one file that translates:

| Size | AWS (`stacks/aws/sizing.tf`) | GCP (`stacks/gcp/sizing.tf`) | vCPU / RAM |
|---|---|---|---|
| `small` | `t3.medium` | `e2-medium` | 2 / 4 GiB |
| `medium` | `m6i.large` | `e2-standard-2` | 2 / 8 GiB |
| `large` | `m6i.xlarge` | `e2-standard-4` | 4 / 16 GiB |

Sizes are matched on vCPU and RAM, not on price — so a "medium" environment
behaves the same on either cloud. If they were matched loosely, "cloud-agnostic"
would be true of the code and false of the running system.

The same file holds the intent translation: `cost_optimized` becomes
`capacity_type = "SPOT"` on AWS and `spot = true` on GCP; `high_availability`
becomes `multi_az` on RDS and `availability_type = "REGIONAL"` on Cloud SQL.

## One artifact, every environment

The frontend is the usual place cloud-agnosticism leaks, because SPAs like to
bake an API URL in at build time — which means one image per environment.

Here nginx owns the `/api` proxy and its upstream comes from an environment
variable rendered at container start
([`frontend/nginx.conf.template`](../frontend/nginx.conf.template)). The React
bundle only ever calls the relative path `/api/ideas`. So:

- one frontend image is promoted unchanged from local to dev to prod;
- there is no CORS configuration, because everything is same-origin;
- the image digest tested in CI is the digest running in production.

## Adding a third provider

The contract is only credible if extending it is cheap. It was tested twice.

**minikube** was added as a third target *without touching the chart*. It has no
Terraform stack at all — there is no infrastructure to provision — so it
implements the delivery half of the contract with a hand-written values file:

```console
$ ls deploy/helm/idea-board/ci/
aws-dev-values.yaml   gcp-dev-values.yaml   minikube-values.yaml
```

That file, plus [`deploy/local/postgres.yaml`](../deploy/local/postgres.yaml) to
stand in for the managed database, is the entire onboarding. The chart, the
images and the application are unchanged. CI renders all three fixtures on every
pull request, so a template that grows a cloud-specific assumption breaks the
build immediately.

**A full third cloud (e.g. Azure)** is a bounded piece of work:

1. Write `modules/azure-{network,kubernetes,database}` — AKS, Azure Database for
   PostgreSQL, VNet — matching the existing modules' output names.
2. Add `stacks/azure/` by copying `stacks/gcp/` and swapping the module sources
   and the `sizing.tf` lookup table.
3. Add `"azure"` to the `cloud` validation in `platform-contract/variables.tf`
   and `keyvault` to the secret-backend branch in
   [`externalsecret.yaml`](../deploy/helm/idea-board/templates/externalsecret.yaml).
4. Add `azure` to the matrix in `.github/workflows/deploy.yml`.

Nothing else changes. The chart's only remaining provider awareness is the
ingress-annotation helper and the secret-store branch — both single, obvious
places, both reached through the contract.

## Where provider names actually appear

Worth auditing honestly, because "cloud-agnostic" claims usually don't survive
one:

| Location | Why it is unavoidable |
|---|---|
| `infra/terraform/modules/{aws,gcp}-*` | The implementations. This is where provider knowledge belongs. |
| `stacks/*/sizing.tf` | One t-shirt-size lookup table per cloud. |
| `_helpers.tpl` → `ingressAnnotations` | ALB, GCE and nginx take different annotations. One helper, three branches. |
| `externalsecret.yaml` → `provider` | Secrets Manager vs Secret Manager auth differ. One stanza. |
| `.github/workflows/deploy.yml` auth steps | OIDC federation is provider-specific by nature. Two steps, `if:`-gated. |

Everywhere else — the application, the images, the chart's 9 other templates,
the deploy script, the AI layer, the policy engine — has no idea which cloud it
is running on.
