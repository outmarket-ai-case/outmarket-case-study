# AI integration

## The one design rule

> **The model proposes. A deterministic policy engine decides.**

Every AI output in this repository passes two gates before it can affect
anything: a JSON schema, and then hand-written code that can veto, clamp or
override it. That single rule is what separates this from a demo, and it is what
makes the three failure modes below survivable rather than fatal:

| Failure | What happens here |
|---|---|
| The API is unreachable | Each stage falls through to a deterministic path. No stage of the pipeline blocks on the API being up. |
| The model hallucinates | Schema validation rejects malformed output; the policy engine rejects unsafe output; findings with no cited evidence are discarded. |
| Someone injects a prompt | The model's only output is a small typed object. It cannot emit a shell command, and the destructive cases are decided before the model is consulted at all. |

Three features, in increasing order of how much I'd trust them unsupervised.

---

## 1. Environment spec compiler — `aiops plan-env`

**The problem.** Sizing an environment is the kind of judgement that gets copied
from the last environment and never revisited. Developers who understand their
service's requirements don't want to think in instance families, and the people
who do think in instance families are a bottleneck.

**What it does.** Developers write intent in
[`platform.yaml`](../platform.yaml) — a plain-English goal, an expected request
rate, an SLO and a monthly budget. Claude proposes a concrete configuration; the
policy engine then judges it.

```
platform.yaml ──▶ Claude ──▶ InfraProposal ──▶ policy engine ──▶ tfvars + Helm values
   (intent)                  (schema-valid)    (approve/clamp/reject)
```

```console
$ aiops plan-env --env prod --cloud aws --out .aiops

=== idea-board / aws / prod ===
proposal source     : ai
estimated cost      : $914/month (budget $1200)
policy decision     : APPROVED
rationale: A 99.9% SLO rules out spot capacity and single-AZ storage...
  remediated: prod.backup_retention: backup_retention_days -> 7
  warning [prod.no_autoscaling]: production without an HPA cannot absorb a spike
```

**Why it isn't a gimmick.** The model's proposal is *advice*, and
[`policy.py`](../ai/aiops/policy.py) is the authority. It enforces invariants the
model is not trusted with:

- a 99.9% SLO **requires** multi-AZ, deletion protection, 3 AZs, 3 nodes, a PDB
  and 7 days of backups;
- `high_availability` and `cost_optimized` are mutually exclusive;
- `node_max_count` is capped, so an autoscaler bug cannot spend without bound;
- cost is **computed** from a static price table and compared to the budget —
  "does this fit the budget" is arithmetic, not a guess.

Three details that took real thought:

**Production is defined by the SLO, not the name.** `is_production_grade` keys
off `availability_percent >= 99.9`. An environment called `staging` that
promises 99.9% gets production guardrails, and nobody dodges them by renaming a
folder. There is [a test](../ai/tests/test_policy.py) for exactly that.

**Remediation iterates to a fixed point.** Clamping `high_availability` to true
doubles the database cost, which can newly violate the budget. A single-pass
fixer would emit a plan that passed one check and broke another, so
`remediate()` re-evaluates until stable — and a budget violation has *no*
mechanical fix, because only a human can decide to shrink the environment or
raise the budget.

**The baseline is not a stub.** With no API key,
`baseline_proposal()` derives a conservative configuration from the intent and
sends it through the same policy engine. The pipeline degrades; it does not stop.

---

## 2. AI release gate — `aiops gate`

**The problem.** "Did that deploy work?" is answered well by rules at the
extremes and badly in the middle. `CrashLoopBackOff` is obvious. So is a
completely clean rollout. The middle — two restarts, a handful of errors in the
logs, a rollout that finished slowly — is where you actually want someone to
*read* the errors, and where rules either page constantly or miss things.

**What it does.**

```
                  ┌──────────────────────────────┐
  evidence  ─────▶│  1. deterministic triage     │
  (kubectl,       └──────┬───────────┬───────────┘
   metrics)              │           │
              hard_fail / clean   ambiguous
                         │           │
                         │           ▼
                         │    ┌──────────────────┐
                         │    │ 2. Claude reads  │
                         │    │    the evidence  │
                         │    └────────┬─────────┘
                         │             │
                         ▼             ▼
                  ┌──────────────────────────────┐
                  │  3. policy override          │
                  │  hard signals beat the model │
                  └──────────────┬───────────────┘
                                 ▼
                     verdict + exit code (0/1/2)
```

**Stage 1 keeps the model out of the clear-cut cases.** A crash loop is a
rollback; a fully-clean rollout is a pass. Neither costs an API call. This is
not only about cost — it means the model is not a single point of failure for
the cases you least want to get wrong. Verified on the live cluster: a healthy
release returns `triage=clean, decided by=deterministic` with **zero** API
calls.

**Stage 2 is where the model earns its place.** It reads pod events, container
logs and Prometheus metrics and returns a typed verdict with cited evidence.

**Stage 3 is the part that makes stage 2 safe.** Deterministic signals win on
conflict, in *both* directions:

- the model cannot call a crash-looping release healthy;
- a rollback recommendation below 0.7 confidence, uncorroborated by any hard
  signal, is downgraded to an alert;
- `health=failed` with `should_rollback=false` is contradictory, so the severity
  wins;
- **findings with no cited excerpt are dropped**, because an unsupported claim
  is what a hallucination looks like.

**Prompt injection is a real threat here**, because log lines come from a
running container and can contain a request body written by an attacker. Three
mitigations: the system prompt says the evidence is untrusted data, the evidence
is fenced, and — most importantly — the model's verdict is structurally unable
to do anything except set a few typed fields. There is a
[fixture](../ai/tests/fixtures/prompt_injection.json) containing a log line that
instructs the model to report the deployment healthy; the
[test](../ai/tests/test_gate.py) asserts the release is still rolled back,
because a crash loop is decided before the model is asked.

**On an API outage the gate never rolls back on a guess.** It reports `degraded`,
leaves the release running and asks for a human. Exit code 2. The one thing an
LLM outage must not do is start reverting production.

Two refinements that only came from running it against a real cluster:

- **Stale events are filtered.** A namespace keeps events for about an hour, and
  judging a fresh release on the previous rollout's failure is how a gate earns
  a reputation for crying wolf.
- **Startup-probe failures are ignored.** A startup probe failing while the
  container boots is the probe doing its job. Counting it made *every* deploy
  triage as ambiguous — which would have sent every rollout to the model and
  thrown away the entire benefit of stage 1. Readiness and liveness failures are
  deliberately still counted: those mean a container that *was* serving has gone
  bad.

---

## 3. ChatOps command planner — `aiops plan-command`

**The problem.** "Use an LLM to generate `kubectl` commands" is the most
commonly suggested and most dangerous version of this idea. A model that emits
shell strings, driven by text from a pull request, is a remote code execution
path with extra steps.

**What it does.** A maintainer comments:

```
/platform deploy a preview of this branch to gcp and check it's healthy
```

and gets back a plan. The model never writes a command. It selects entries from
an [operation catalogue](../ai/aiops/commands.py) and fills their typed
parameters; the catalogue renders `argv`.

```console
intent      : deploy_preview
plan:
  1. deploy
     $ scripts/deploy.sh gcp pr-42 sha-abc1234
  2. wait_rollout
     $ kubectl rollout status deploy/idea-board-backend -n idea-board-pr-42 --timeout=5m
  3. run_gate
     $ python -m aiops gate --namespace idea-board-pr-42 --release idea-board
```

**Why this is defensible.** Four independent controls:

1. **Authorisation** — the workflow only obeys commenters with write access.
2. **The allowlist** — an operation not in the catalogue is rejected. The worst
   a confused or injected model can do is pick a *wrong allowlisted operation
   with valid parameters*.
3. **Typed parameters** — every argument goes through a validator. `pr-1;rm -rf /`
   fails the Kubernetes-name check.
4. **No shell** — operations render `argv` lists, executed directly. The
   [workflow](../.github/workflows/ai-preview.yml) reads argv into a bash array
   and executes it without interpretation, so even a metacharacter that somehow
   passed validation would be a literal argument.

On top of that, destructive operations (`rollback`, `teardown_preview`,
`scale_backend`) require an explicit `--approve`, and **one rejected step
invalidates the whole plan** — executing steps 1 and 3 while skipping 2 leaves
the system in a state nobody planned.

**This is the one stage with no deterministic fallback.** If the model is
unavailable, planning fails. Guessing what a developer meant is precisely the
thing that must not be improvised.

---

## Engineering the API integration

All model access goes through [`llm.py`](../ai/aiops/llm.py):

- **Structured outputs.** Pydantic models are compiled to JSON Schema and
  hardened for the API's subset (`additionalProperties: false` everywhere, all
  properties required, unsupported keywords stripped). The numeric and length
  constraints move from generation-time to validation-time — Pydantic still
  enforces them, so a model returning `node_count: 0` fails validation rather
  than reaching Terraform. [Tested](../ai/tests/test_llm.py).
- **Refusals are handled.** Claude Opus 5 runs safety classifiers, and log
  analysis sits close enough to security content to risk a false positive. A
  refusal is a normal HTTP 200, so `stop_reason` is checked *before* reading
  content, and server-side fallbacks re-serve a declined request on another
  model inside the same call.
- **One recoverable exception.** Every failure — transport, refusal, empty
  response, schema violation — becomes `LlmUnavailable`, and every caller has a
  documented fallback.
- **Adaptive thinking + `effort: high`.** These decisions gate production
  deploys; the token cost is rounding error next to a bad rollout.

## Testing an AI system

65 tests, and **not one of them calls the API**. The model is stubbed and the
evidence comes from checked-in fixtures, which means the decision logic — the
part that can actually hurt you — is covered deterministically, in CI, on every
pull request, for free.

That is the practical argument for this whole architecture. Because the model
only ever *proposes*, everything that *decides* is ordinary code, and ordinary
code can be tested.

## What I deliberately did not build

- **AI-generated Terraform.** Generating HCL is a demo; generating *validated
  variables* for reviewed modules is useful. The blast radius of a hallucinated
  `aws_iam_policy` is unbounded; the blast radius of a hallucinated
  `node_count` is one clamped integer.
- **An autonomous remediation agent.** The gate recommends and can revert to a
  known-good revision. It cannot invent a fix and apply it.
- **AI in the request path.** Nothing in the running application calls a model.
  The AI is in the *platform*, where a slow or failed call delays a deploy
  instead of an end user.
