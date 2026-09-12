# Deployment flow, end to end

Three targets — Docker Compose, minikube, and a real cloud — and one claim worth
making precisely:

> **Provisioning and configuration differ per target. The images, the chart, the
> migration path and the readiness contract do not.**

Everything to the left of the merge below is target-specific. Everything to the
right of it is identical, which is what makes a local run meaningful evidence
about a cloud one.

```
                            git push / pull request
                                       │
                    ┌──────────────────▼───────────────────┐
                    │  ci.yml                              │
                    │  pytest · vitest · tsc               │
                    │  tofu validate (aws, gcp)            │
                    │  helm lint × 3 contract fixtures     │
                    │  docker build backend + frontend     │
                    └──────────────────┬───────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
  DOCKER COMPOSE                   MINIKUBE                       AWS / GCP
        │                              │                              │
   ┌────▼─────┐                  ┌─────▼──────┐              ┌────────▼────────┐
   │ provision│                  │ provision  │              │ provision       │
   │  none    │                  │ in-cluster │              │ terraform apply │
   │          │                  │ Postgres   │              │ VPC · K8s · DB  │
   └────┬─────┘                  └─────┬──────┘              └────────┬────────┘
        │                              │                              │
   ┌────▼─────┐                  ┌─────▼──────┐              ┌────────▼────────┐
   │ configure│                  │ configure  │              │ configure       │
   │ .env +   │                  │ ci/        │              │ platform        │
   │ compose  │                  │ minikube-  │              │ contract (JSON) │
   │ defaults │                  │ values.yaml│              │ ↓ platform-     │
   │          │                  │            │              │   values.sh     │
   └────┬─────┘                  └─────┬──────┘              └────────┬────────┘
        │                              │                              │
        │                              └──────────────┬───────────────┘
        │                                             │
        │                              ┌──────────────▼───────────────┐
        │                              │  helm upgrade --install      │
        │                              │  --atomic --wait             │
        │                              │  deploy/helm/idea-board      │  ← one chart,
        │                              └──────────────┬───────────────┘    both targets
        │                                             │
   ┌────▼──────────┐                   ┌──────────────▼───────────────┐
   │ migrate       │                   │ init container               │
   │ service       │                   │ alembic upgrade head         │
   │ (runs to      │                   │ Postgres session advisory    │
   │  completion)  │                   │ lock serialises replicas     │
   └────┬──────────┘                   └──────────────┬───────────────┘
        │                                             │
        └──────────────────────┬──────────────────────┘
                               │   ← same Alembic revision, same lock,
                               │     in all three targets
                 ┌─────────────▼──────────────┐
                 │ readiness                  │
                 │ SELECT 1 FROM ideas        │  ← not SELECT 1: a pod that
                 │ (compose: healthcheck)     │    failed to migrate is not ready
                 └─────────────┬──────────────┘
                               │
                 ┌─────────────▼──────────────┐
                 │ serving                    │
                 └─────────────┬──────────────┘
                               │
                 ┌─────────────▼──────────────┐
                 │ aiops gate                 │  ← cloud + minikube
                 │ triage → AI → override     │    exit 1 triggers
                 │ rollback on a bad verdict  │    helm rollback
                 └────────────────────────────┘
```

## What actually differs

| | Docker Compose | minikube | AWS / GCP |
|---|---|---|---|
| **Provisioning** | none | in-cluster Postgres StatefulSet | `terraform apply` — VPC, cluster, managed Postgres, registry, identity |
| **Config source** | `.env` + compose defaults | `ci/minikube-values.yaml` | the Terraform `platform` contract, mapped by `platform-values.sh` |
| **Secret** | env var in the compose file | Kubernetes Secret in the local manifest | cloud secret store, resolved in-cluster by External Secrets |
| **Identity** | none | none | IRSA / Workload Identity |
| **Registry** | local Docker daemon | minikube's Docker daemon | ECR / Artifact Registry |
| **Image tag** | build-local | `:local` — **mutable** | `sha-<commit>` — **immutable** |
| **Ingress** | published port 8080 | `nginx` ingress class | `alb` / `gce` |
| **Deploy command** | `docker compose up` | `helm upgrade --atomic` | `helm upgrade --atomic` (via `scripts/deploy.sh`) |
| **Rollback on failure** | none | `--atomic` + AI gate | `--atomic` + AI gate |

The mutable-tag row is the one that bites in practice: because `:local` never
changes, an unchanged release leaves the pod spec identical and Helm has nothing
to roll, so `scripts/minikube-up.sh` issues an explicit `rollout restart` after
building. Cloud deploys use an immutable sha tag and never need it.

## The three commands

```bash
# Docker Compose — everything on one machine, ~2 minutes
docker compose up --build -d
open http://localhost:8080

# minikube — real Kubernetes, same chart as the cloud, ~5 minutes cold
scripts/minikube-up.sh
kubectl -n idea-board-local port-forward svc/idea-board-frontend 8081:80

# a cloud — provision, then deploy
terraform -chdir=infra/terraform/stacks/aws init \
  -backend-config="bucket=$TF_STATE_BUCKET" \
  -backend-config="key=idea-board/dev/terraform.tfstate"
terraform -chdir=infra/terraform/stacks/aws apply \
  -var-file="$PWD/infra/terraform/envs/aws-dev.tfvars"
scripts/deploy.sh aws dev "sha-$(git rev-parse --short HEAD)"
```

`scripts/deploy.sh` is worth reading for the point it proves: it reads the
contract, executes the `kubeconfig_command` the contract hands it, renders the
values, and runs Helm. There is no `if aws … elif gcp` anywhere in it.

## Why the local path is evidence, not a toy

The three targets share the artifact, the chart, the migration and the readiness
definition. So a bug in any of those surfaces locally — and several did:

- the migration that reported success and applied nothing,
- nginx crash-looping under a read-only root filesystem,
- nginx dropping every security header,
- a liveness probe restarting a healthy database.

None of those were visible from `helm template` or from reading the code. What
the local path *cannot* tell you is anything about the parts that differ: IAM,
the secret store, multi-AZ failover, real ingress controllers. Those are
validated (`terraform validate`, rendered chart fixtures) but **not exercised**,
and that distinction is stated in the [README](../README.md#verification) rather
than blurred.
