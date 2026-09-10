# Scalability

## Capacity model

One backend replica runs 2 uvicorn workers and serves roughly **50 rps** for
this workload. The policy engine sizes for **2× headroom** over stated peak:

```
required_replicas = ceil(expected_rps × 2 / 50)
```

| Environment | Peak | Required | Configured | Autoscaling |
|---|---|---|---|---|
| dev | 5 rps | 2 (SLO floor) | 2 | off |
| prod | 200 rps | 8 | 8 | HPA 8 → 16 at 70% CPU (capped by the connection rule) |

The 2-replica floor is not about throughput. Any SLO of 99% or higher needs two
replicas because with one, **every pod eviction is downtime** — and evictions
happen on every node upgrade, not just on failure.

## What scales, and what does not

**Stateless and horizontal.** Frontend and backend hold no session state, so
they scale on replica count alone. The frontend is static assets plus an nginx
proxy and is effectively free to scale.

**The database is the ceiling.** Everything above it scales out; Postgres scales
*up*, plus read replicas.

## The connection ceiling — the real wall

This is the constraint that bites first, and it is arithmetic, not opinion:

```
per replica  = db_pool_size (5) + db_max_overflow (5) = 10 connections
prod at 8    = 80 connections
prod at 24   = 240 connections          ← HPA maximum
Postgres default max_connections        ≈ 100
```

**The HPA can scale the application into database connection exhaustion.** At 8
replicas prod uses 80 of ~100 connections; the autoscaler is permitted to reach
24 replicas, which needs 240. The failure mode is ugly — new pods start, fail to
acquire connections, and readiness fails while the database refuses new work.

Three ways to fix it, in order of preference:

1. **Add a connection pooler** (PgBouncer in transaction mode) so replica count
   and backend connections decouple. This is the correct fix and is not built.
2. **Raise `max_connections`** on a larger instance — each connection costs
   memory, so this trades RAM for headroom.
3. **Lower `db_pool_size`** per replica and accept more connection churn.

**This is now enforced.** Writing this document surfaced the gap, so the policy
engine gained a `capacity.db_connections` rule that compares
`maxReplicas × (pool + overflow)` against the instance's usable connection
limit (80% of `max_connections`, leaving room for migrations and psql
sessions). It checks the autoscaler's *maximum*, not the current replica count,
because the failure only appears under the load that triggers scale-up — the
worst possible moment to discover it.

It fires on the real production plan:

```console
$ python -m aiops plan-env --env prod --cloud aws
  remediated: capacity.db_connections: autoscaling_max_replicas -> 16
```

So prod now autoscales 8 → **16**, not 8 → 24: the ceiling is set by what the
database can actually serve. Raising it requires a bigger instance or a pooler,
which is the correct conversation to force.

## Node capacity

Backend requests 50m CPU / 128Mi; frontend 10m / 32Mi. A `medium` node
(2 vCPU / 8 GiB) holds far more replicas than the HPA will create, so pod
scheduling is not the binding constraint — nodes scale for redundancy and
eviction headroom rather than for density.

`node_max_count` is capped at **20 in every environment** so an autoscaler bug
cannot spend without bound. That cap is enforced by the policy engine, not by
convention.

## Scaling the platform, not just the app

- **Adding an environment** is an entry in `platform.yaml` plus one `plan-env`
  run.
- **Adding a cloud** is three role modules that satisfy the platform contract —
  minikube was added as a third target with no chart change.
- **Adding a service** would need its own chart; the contract, pipeline and AI
  layer are reusable as-is.

## Not measured

No load test has been run. The 50 rps/replica figure is a reasoned estimate for
an async FastAPI service doing one indexed query per request, **not a measured
number** — and the honest next step before trusting the capacity table is to
put `k6` or `locust` in front of it and replace that constant with data.

Also unmeasured: `GET /api/ideas` currently has no pagination beyond a `limit`
cap of 500 and no cache, so a very large board would degrade linearly.
