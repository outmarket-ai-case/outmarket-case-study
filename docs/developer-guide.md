# Application developer guide

You are here to ship application code, not to operate a platform. This is the
short version of everything you need, and the longer version of the two things
that will actually confuse you the first time.

**Everything below is doable from a browser.** A terminal is optional and only
speeds up the inner loop.

---

## The loop

```
  edit code ──▶ run it locally ──▶ open a PR ──▶ see it on dev ──▶ merge ──▶ prod
                  (1 command)       (automatic)    (1 form)      (review)  (approval)
```

## Running it locally

Two options. Neither needs a cloud account or a secret.

```bash
docker compose up --build -d          # everything on one machine, ~2 min
open http://localhost:8080
```

```bash
scripts/minikube-up.sh                # real Kubernetes, the same chart as prod
kubectl -n idea-board-local port-forward svc/idea-board-frontend 8081:80
```

Use Compose for a quick check of application behaviour. Use minikube when you
touched anything in `deploy/helm/`, a probe, a migration, or a Dockerfile —
it runs the *same chart* the clouds run, so those break here too. Four of the
most instructive bugs in this project were found on minikube and would have
reached a cloud otherwise.

## Opening a pull request

Push the branch and open the PR. Three things happen on their own:

| | Runs when | Gives you |
|---|---|---|
| **ci** | always | backend + frontend tests, `terraform validate`, `helm lint`, image builds |
| **infra · plan** | you touched `infra/terraform/**` | a Terraform plan, commented on the PR |
| **ai-env-plan** | you touched `platform.yaml` | proposed sizes, monthly cost, policy verdict |

If `ci` is red, open the failing job and read the log. Nothing else is gated on
you until a human reviews.

## Seeing your branch on dev

**Actions → deploy → Run workflow.** In *"Use workflow from"* pick **your
branch**, environment `dev`, clouds `aws`.

About six minutes later the run's **Summary** tab shows the live URL, the image
tag and the pod list. Click the URL.

Two things worth knowing about this:

- **It does not run your tests.** `deploy` builds and ships; `pytest` and
  `vitest` live in `ci`. Open the PR *first* and the two run in parallel, so a
  green PR and a working URL mean the same thing.
- It uses the workflow file **from your branch**, so edits to
  `.github/workflows/` take effect immediately — which is convenient for
  iterating and worth remembering when something behaves unexpectedly.

## Shipping

Get the PR reviewed, merge it, and stop. **release** takes over: it deploys to
dev, lets the AI gate judge the result, then waits for an approval before
production and again before the production deploy lands.

If it stops after dev, it is waiting on a reviewer — not broken.

---

## Debugging

### Start here

Whatever went wrong, the run's **Summary** tab usually says. The deploy job
writes the URL, the image tag, and `kubectl get deploy,pods` output into it, and
the AI gate writes its verdict and the evidence it used.

### A deploy went red

It already rolled back. The previous version is still serving — `--atomic`
reverts a failed release, and the gate triggers `helm rollback` on a bad
verdict. Nothing is half-applied.

Read the gate's section of the summary: it names the pods, the events and the
log lines it based the verdict on.

### Pods will not become ready

Almost always the readiness probe, and almost always for a good reason.
`/readyz` runs `SELECT 1 FROM ideas` — it queries the **application table**, not
the connection. So a pod that failed to migrate deliberately never reports
ready, which is the system telling you the schema is wrong rather than serving
500s to users.

```bash
kubectl -n idea-board-dev logs <pod> -c migrate    # the init container
kubectl -n idea-board-dev describe pod <pod>       # events, probe failures
```

### CrashLoopBackOff on the frontend

The image runs with a read-only root filesystem. nginx needs writable mounts at
`/tmp`, `/var/cache/nginx` and `/etc/nginx/conf.d`; miss one and it dies at
startup. Check `kubectl logs` for a permission error on a path.

### "has no platform contract in its Terraform state"

That environment was never provisioned, or was provisioned against a different
state key. Run **infra** with `action: plan`, read it, then `action: apply`.
Provisioning is a separate workflow from shipping on purpose.

### Healthcheck fails but the service works

Use `127.0.0.1`, not `localhost`. In an image where `localhost` resolves to
`::1` first, a healthcheck against an IPv4-only listener fails while everything
else is fine.

### A probe restarts something healthy

Exec probes default to `timeoutSeconds: 1`. `pg_isready` has to fork a process,
and three slow probes had the kubelet restarting a perfectly healthy database
every sixty seconds here. The tell is `exitCode: 0` in the restart reason — an
OOM kill would be `137`.

### Judge a release the way CI does

```bash
cd ai && python -m aiops gate --namespace idea-board-local --release idea-board
```

Works against any cluster including minikube, and needs no API key — without
one it falls through to a deterministic verdict.

---

## Where things live

| I want to change... | Edit |
|---|---|
| API behaviour | `backend/app/routers/` |
| The database schema | `backend/models.py` **and** a new `backend/migrations/versions/` revision |
| The UI | `frontend/src/` |
| Replica counts, probes, resources | `deploy/helm/idea-board/values.yaml` |
| An environment's size or cost | `platform.yaml` — in English; the pipeline compiles it |
| Cloud resources | `infra/terraform/` — and expect a plan on your PR |

## Things that will surprise you once

**The schema is owned by Alembic, not `create_all`.** Adding a column to
`models.py` does nothing on its own. Generate a migration, or the column will
not exist and `/readyz` will keep your pod out of the load balancer.

**Migrations run in an init container on every backend pod.** They serialise
through a Postgres advisory lock, so replicas starting together is fine.

**`:local` is mutable, `sha-<commit>` is not.** On minikube a rebuilt image
leaves the pod spec unchanged, so Helm has nothing to roll —
`scripts/minikube-up.sh` issues an explicit `rollout restart`. Cloud deploys use
an immutable tag and never need it.

**Nothing in the app knows which cloud it is on.** Everything
provider-shaped arrives through the platform contract. If you find yourself
writing `if aws … elif gcp` in application code, the value you want belongs in
the contract instead.

## When to ask rather than guess

- `drift` is red on a Monday — someone changed cloud resources by hand. Do not
  apply anything; raise it.
- A plan says "N to add" on an environment that already exists — stop. The plan
  header states whether the environment has existing state; if it says it has
  none and you know it does, the backend configuration is wrong.
- You need a new environment — it starts with a `platform.yaml` change and a
  PR, not with Terraform.
