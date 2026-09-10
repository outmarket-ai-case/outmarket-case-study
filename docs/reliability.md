# Reliability

## Targets

| Environment | Availability | p95 latency | RPO | RTO |
|---|---|---|---|---|
| dev | 99.0% (~7h/month) | 500 ms | 24h (daily backup) | best effort |
| prod | 99.9% (~43min/month) | 300 ms | ≤5 min (PITR window) | ~2 min (automated rollback) |

`is_production_grade` keys off the **SLO, not the environment name**. An
environment called `staging` that promises 99.9% gets production guardrails, and
nobody can dodge them by renaming a folder.

## Failure scenarios

Each row is a real mechanism in this repository, not an aspiration.

| Failure | What happens | Blast radius |
|---|---|---|
| **A pod crashes** | Liveness probe restarts it. `/healthz` never touches the database, so a database blip cannot cause a restart storm. | None — other replicas serve. |
| **A pod goes unready** | Readiness fails, it leaves the Service endpoints, traffic drains to healthy replicas. | None. |
| **A node dies** | `topologySpreadConstraints` keep replicas on different nodes and zones, so the remaining replicas absorb it; the autoscaler replaces the node. | Brief capacity dip. |
| **A node is drained** | `PodDisruptionBudget` (prod) blocks a drain that would take the service below `minAvailable`. | None. |
| **An AZ is lost** | 3 AZs, multi-AZ Postgres fails over, NAT per AZ so the surviving zones keep egress. | Elevated latency during failover (~60–120s for RDS/Cloud SQL). |
| **A bad image ships** | `helm upgrade --atomic` with `maxUnavailable: 0` — new pods must pass readiness before old ones go, and a failed rollout is reverted automatically. | None: users never see the new pods. |
| **A subtly bad release** (starts fine, misbehaves) | The AI release gate reads events, logs and metrics and rolls back on a hard signal or an adjudicated failure. | Bounded by gate latency. |
| **A migration fails** | Init container exits non-zero, the pod never becomes ready, `--atomic` reverts the release. Schema changes are transactional. | None. |
| **Replicas race on migration** | A Postgres session-level advisory lock serialises them; the rest find the schema at head and no-op. | None. |
| **A migration pod is OOM-killed mid-migration** | Postgres releases a *session*-level lock when the connection dies, so the next rollout is not wedged. | None. |
| **The model API is down** | Every stage falls through to its deterministic path. The gate reports `degraded`, leaves the release running, and asks for a human — it never rolls back on a guess. | None; a human decides. |
| **The secret store is unreachable** | External Secrets keeps serving the last synced Kubernetes Secret; new pods fail readiness rather than starting misconfigured. | Degraded scale-up only. |

## What actually happened during development

Three of these were not theoretical — they are why some of the mechanisms above
exist.

**Postgres restarted six times** while running locally (Docker Desktop churn).
It recovered unattended every time and no idea was lost, because the data is on
a PersistentVolume rather than in the container.

**A migration reported success and applied nothing.** Acquiring the advisory
lock issued a statement, which opened an implicit transaction; Alembic's own
transaction nested inside it and the DDL was discarded when the connection
closed. The init container exited 0. This is the worst class of failure — silent
— and it produced two fixes: explicit commits, and **`/readyz` now queries the
application table** rather than running `SELECT 1`. A connectivity check passes
against an un-migrated database; a real query does not. Readiness now means "can
serve traffic", so a bad migration fails the rollout instead of reaching users.

**nginx crash-looped under a read-only root filesystem** because the
unprivileged image writes proxy temp files to `/tmp`. Caught only by deploying.

**A liveness probe restarted a healthy database eleven times.** The local
Postgres probes used the default `timeoutSeconds: 1`, and an exec probe has to
fork a process — on a memory-pressured node `pg_isready` regularly took longer
than a second. Three misses tripped liveness, the kubelet SIGTERMed Postgres,
and it exited cleanly (`exitCode: 0`, `reason: Completed`) roughly every 60
seconds. The tell was the exit code: an OOM kill is 137, so a clean 0 meant
something was *asking* it to stop.

Two lessons, both now in the manifest:

- **Set `timeoutSeconds` explicitly on exec probes.** The 1-second default is
  unrealistic for anything that forks.
- **A liveness probe on a database should be very reluctant.** Ours now needs
  ~2 minutes of sustained failure before restarting. A trigger-happy liveness
  probe turns a slow query into a restart loop, which is worse than the stall
  it was meant to catch. Readiness is the probe that should react fast — it
  removes the pod from endpoints without destroying state.

This one also demonstrates the earlier fix working: readiness now queries the
application table, so while Postgres was flapping the backends correctly
refused to report ready, and `helm --atomic` refused to complete the rollout.
The instability was *surfaced* rather than shipped.

## Rollout safety, concretely

```yaml
strategy:
  rollingUpdate:
    maxUnavailable: 0     # never drop below current capacity
    maxSurge: 1
startupProbe:  { failureThreshold: 20, periodSeconds: 3 }   # 60s to boot
readinessProbe:{ path: /readyz }   # queries the ideas table
livenessProbe: { path: /healthz }  # never touches the database
```

The three-probe split is deliberate. A single probe forces one timeout to serve
two incompatible purposes — tolerating a slow start and detecting a wedged
process — and the usual result is either restart storms or hung pods.

## Known gaps

- **Local Postgres is a single replica** on a hostPath volume. Fine for a demo,
  not something to lean on. The cloud stacks use managed multi-AZ Postgres.
- **Single region.** Surviving a full region loss would need cross-region
  replication and a second cluster; neither is built.
- **No chaos testing.** The scenarios above are reasoned from the manifests and,
  where marked, observed. Pod and node failure have been exercised; **AZ loss
  and database failover have not**, because that needs a real cloud deployment.
- **No alerting.** Metrics are exposed and the gate reads them at deploy time,
  but nothing pages anyone between deploys.
