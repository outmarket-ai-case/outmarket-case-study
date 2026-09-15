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

## Provisioning through the pipeline

Two pipelines, not one, and the split is the design decision worth defending:

| | Runs | Blast radius | Gate |
|---|---|---|---|
| **infra** | when a resource changes — first stand-up, a new environment, a bigger database | can delete a database | reviewed plan + `infra-<env>` approval |
| **release** | every merge to `main` | one Helm release, reverts itself | `promote-prod` + `prod` approval |

Chaining them would be tidier to draw and worse to operate: every routine
frontend merge would carry the authority to apply Terraform to production.
Separating them means the permission to change infrastructure is exercised only
when someone means to.

```
  infra.yml                                  release.yml
  ─────────                                  ───────────
  PR ─▶ plan, commented                      merge ─▶ deploy·dev + AI gate
        │                                                 │
   review + merge                                   [promote-prod]
        │                                                 │
   dispatch apply ─▶ [infra-<env>] ─▶ terraform      deploy·prod + AI gate
        │                                  │
        └──▶ platform contract in state ───┴─ ─ ─ ─▶ read by deploy at run time
                                                     (the only coupling)

  drift.yml ─▶ the same plan, every Monday, red if reality moved
```

`deploy` reads the contract and never writes it, and checks it exists first: a
deploy to an un-provisioned environment says so and points at the `infra`
dispatch, rather than dying inside a `jq` filter on an empty string.

Three properties worth stating precisely, because they are the ones that
usually go wrong:

**An apply never re-plans.** The plan job uploads its binary plan; the apply job
downloads it and runs `terraform apply tfplan` with no `-var-file`. A saved plan
already contains every value, so re-passing them would be the only way the
applied change could differ from the reviewed one — including across the hours
an approval may sit waiting.

**The gates are not in the YAML.** Each approval is a GitHub Environment with
required reviewers. A pull request therefore cannot weaken its own gate, and
`.github/workflows/` is itself covered by CODEOWNERS.

**Decoupling costs drift detection, so it is bought back explicitly.** A
pipeline that plans on every merge notices a console change for free. This one
doesn't, so `drift.yml` runs the same plan on a schedule across every cloud and
environment and fails the leg that moved. Naming what a design choice costs, and
paying for it deliberately, is the difference between a trade-off and an
oversight.

Creating a new environment is three reviewable steps: add its intent to
`platform.yaml`, let **ai-env-plan** compile that into a tfvars file and merge
it, then dispatch **infra** with `action: apply`.

## The three commands

```bash
# Docker Compose — everything on one machine, ~2 minutes
docker compose up --build -d
open http://localhost:8080

# minikube — real Kubernetes, same chart as the cloud, ~5 minutes cold
scripts/minikube-up.sh
kubectl -n idea-board-local port-forward svc/idea-board-frontend 8081:80

# a cloud — once, to provision
gh workflow run infra.yml -f cloud=aws -f environment=dev -f action=plan
gh workflow run infra.yml -f cloud=aws -f environment=dev -f action=apply

# a cloud — thereafter, merging to main ships it; this is the break-glass form
gh workflow run release.yml -f clouds=aws -f promote=false
```

The second command is `scripts/deploy.sh aws dev sha-<commit>` underneath, and
that script still runs perfectly well by hand against a provisioned
environment — the workflow is where it belongs, not where it is confined to.

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
