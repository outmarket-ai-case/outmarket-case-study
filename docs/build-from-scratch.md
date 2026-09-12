# Building this from scratch

The order matters more than the code. Each step below leaves you with something
you can actually run, which is how you catch the bugs that only appear once a
thing is deployed — four of the most instructive bugs in this project were
invisible from reading the source.

The companion video walks the same path through the real files:
**`demo/out-tutorial/idea-board-tutorial.mp4`**.

| # | Build | You can run it when |
|---|---|---|
| 1 | FastAPI app + Alembic migration | `pytest` passes against SQLite |
| 2 | Dockerfiles + `docker-compose.yml` | the stack answers on `:8080` |
| 3 | React frontend behind nginx | posting an idea works end to end |
| 4 | Helm chart + minikube values | it runs on real Kubernetes |
| 5 | `platform-contract` module | the shape is agreed before any cloud |
| 6 | One cloud's three role modules | `terraform validate` passes |
| 7 | `platform-values.sh` + `deploy.sh` | you can deploy to that cloud |
| 8 | The second cloud | the two-line tfvars diff holds |
| 9 | `aiops` policy engine, then the gate | tests pass with no API key |
| 10 | GitHub Actions | a push deploys and is judged |

**Build the contract at step 5, not step 8.** Retrofitting a contract onto two
finished stacks is far harder than agreeing the shape before the second one
exists — you end up reshaping working Terraform to fit a shape you should have
designed first.

---

## 1. The application

Write `config.py` first and make it read everything from the environment. No
cloud SDK, no metadata lookups. That single decision is what later lets one
image run unchanged on Compose, minikube, EKS and GKE.

Then, in order: `db/session.py` (async engine created and disposed with the app
lifespan), `models.py`, `schemas.py`, `routers/ideas.py`.

Two things worth getting right immediately, because retrofitting them is
painful:

**The schema is owned by Alembic**, not by `create_all`. Say so in a comment in
`models.py` so nobody adds a convenience call later.

**Three probes, three jobs** — `routers/health.py`:

| Probe | Path | Checks | Why |
|---|---|---|---|
| Startup | `/healthz` | nothing | absorbs a slow boot so liveness can stay tight |
| Liveness | `/healthz` | **never the database** | a database blip must not restart every pod at once |
| Readiness | `/readyz` | `SELECT 1 FROM ideas` | a pod that failed to migrate must not report ready |

Readiness querying the *application table* rather than `SELECT 1` is not
pedantry. A connectivity check passes against an un-migrated database, which is
exactly how a migration that silently applied nothing reached a running pod
here.

**Check:** `pytest -q` green against SQLite, with no database container.

## 2. Packaging

Multi-stage Dockerfiles: build wheels or bundles in a throwaway stage so no
compiler reaches the runtime image. Run as a non-root UID, read-only root
filesystem, all capabilities dropped.

Two traps, both of which cost real debugging time here:

- **A read-only root filesystem needs explicit writable mounts.** nginx writes
  proxy temp files to `/tmp`, caches to `/var/cache/nginx`, and a rendered
  config to `/etc/nginx/conf.d`. Miss one and it crash-loops at startup.
- **Healthchecks should use `127.0.0.1`, not `localhost`.** In an image where
  `localhost` resolves to `::1` first, a healthcheck against an IPv4-only
  listener fails while the service works perfectly.

In `docker-compose.yml`, make migrations a **one-shot `migrate` service** that
runs to completion before the backend starts. That mirrors the init container
you will write in step 4, and mirroring the topology is what stops the local and
cluster paths drifting.

**Check:** `docker compose up --build -d`, then `curl localhost:8000/api/ideas`.

## 3. The frontend

Make every API path **relative**. nginx owns the `/api` proxy in every image and
takes its upstream from an environment variable at container start, so there is
no build-time API URL and no CORS — and the bundle CI tested is the bundle
production runs.

In the nginx config, compute `Cache-Control` with a `map` rather than an
`add_header` inside each `location`. An `add_header` in an inner block
**replaces** every inherited header instead of merging, which silently dropped
the security headers on exactly the responses that serve HTML.

**Check:** post an idea in the browser and see it persist across a reload.

## 4. Kubernetes

Write the chart so that **every cloud-shaped value arrives under one key**,
`.Values.platform`. Even before any cloud exists, this forces the discipline
that makes step 5 possible.

The parts that matter:

- **Migrations as an init container**, not a Helm hook. A `pre-install` hook Job
  needs the ServiceAccount and the secret-derived `DATABASE_URL`, both of which
  Helm creates *after* hooks run. An init container inherits them by
  construction.
- **A Postgres session-level advisory lock** in `migrations/env.py` so replicas
  starting together serialise. Session-level, not transaction-level: Postgres
  releases it when the connection dies, so an OOM-killed migration pod cannot
  wedge the next rollout.
- **`maxUnavailable: 0`** so a new pod must pass readiness before an old one is
  removed, and `helm upgrade --atomic` so a failed rollout reverts itself.
- **A PodDisruptionBudget**, which governs *other people's* disruption — node
  drains and cluster upgrades — not your own rollout.

Then stand it up on minikube with an in-cluster Postgres. Set
**`timeoutSeconds` explicitly on exec probes**: the default is one second,
`pg_isready` has to fork a process, and three slow probes had the kubelet
restarting a healthy database every sixty seconds here.

**Check:** `scripts/minikube-up.sh`, then post an idea through a port-forward.

## 5. The platform contract

This is the step that makes everything after it easy.

Define one module whose only job is to emit a **normalised object** describing
the environment: cluster, registry, database, identity annotations, ingress
class, and a `schema_version`. Two rules:

- **Generalise the vocabulary.** `account_id`, not `project_id` — otherwise
  GCP's noun leaks into an AWS deployment.
- **Carry commands as opaque strings.** `cluster.kubeconfig_command` is executed
  by the deploy script, which is why that script needs no provider branching at
  all.

## 6. One cloud

Organise modules by **role** — network, kubernetes, database — not by cloud.
Write one cloud's three, wire them in a thin `stacks/<cloud>` root, and have the
root feed the contract module.

The variable contract is cloud-neutral: **t-shirt sizes and boolean posture**
(`node_size = "medium"`, `high_availability = true`), never a machine type. A
per-stack `sizing.tf` maps a size to `m6i.large` or `e2-standard-2`, matched on
vCPU and RAM so an environment behaves the same on either cloud.

Use a **partial backend** (`backend "s3" {}`) with the bucket passed at `init`,
so nothing environment-specific is hardcoded.

For secrets: generate the password in Terraform, write it to the cloud secret
store, and **export only a reference**. It should never be a Terraform output,
which keeps it out of state, plans, CI logs and values files.

**Check:** `terraform validate`, and a rendered chart against a contract fixture.

## 7. The seam

Two scripts:

- **`platform-values.sh`** — about thirty lines of `jq` mapping the contract to
  Helm values. This is the entire boundary between infrastructure and delivery.
  Have it refuse to run against a `schema_version` it does not speak.
- **`deploy.sh`** — reads the contract, executes the `kubeconfig_command` it
  finds there, renders values, runs Helm. Read it afterwards looking for
  `if aws … elif gcp`. There should be none.

## 8. The second cloud

Implement the same three role interfaces with the other provider's services and
fill the same variable contract. If step 5 was done properly, nothing in
`deploy/`, `scripts/` or CI changes.

**Check:** the diff between the two dev tfvars files is two lines — a region and
GCP's project id.

## 9. The AI layer

Build it in this order, because it is the order of decreasing trust:

1. **The schemas** (`models.py`) — the complete, narrow, typed surface the model
   is allowed to emit. It cannot invent a field.
2. **The policy engine** (`policy.py`) — a pure function: proposal in, findings
   out. No cloud calls, no model. This is the half that *decides*.
3. **The LLM client** (`llm.py`) — structured outputs, explicit refusal
   handling, and one recoverable exception every caller degrades from.
4. **The gate** (`gate.py`) — deterministic triage first, the model only for the
   ambiguous middle, then policy override in both directions.

The rule to hold onto: **the model proposes, deterministic code decides.**
Because of it, ninety tests cover the decision logic without ever calling the
API — stub the client and use checked-in evidence fixtures, including one whose
logs try to talk the model into reporting a broken deploy as healthy.

## 10. Automation

Four workflows: CI on every PR (tests, `terraform validate`, `helm lint` against
each contract fixture, image builds — no secrets, so it runs on forks), a deploy
workflow using **OIDC federation** rather than static keys, and the two that
drive the AI layer.

Build once, deploy many: the image digest CI tested is the digest that reaches
production, and configuration comes from the contract at deploy time.

---

## What to expect to get wrong

These all happened here, and none were visible from reading code or running
`helm template`:

| Symptom | Cause |
|---|---|
| Migration logs success, table does not exist | the advisory lock's implicit transaction swallowed the DDL |
| Security headers missing on HTML only | `add_header` in a `location` replaces inherited headers |
| nginx crash-loops | read-only root filesystem, no `/tmp` mount |
| Healthcheck fails on a working service | `localhost` resolved to `::1`, listener is IPv4 |
| A healthy database restarts every 60s | exec probe with the default `timeoutSeconds: 1` |
| Every deploy looks "degraded" | counting startup-probe failures that happen on every rollout |

The pattern is worth internalising: each was found by deploying and then looking
at something specific — an exit code, a response header, an event timestamp.
That is the argument for step-by-step verification rather than building the
whole thing and running it once at the end.
