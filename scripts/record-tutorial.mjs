/**
 * Records the code-walkthrough tutorial.
 *
 *   node scripts/record-tutorial.mjs [--out demo/out-tutorial]
 *
 * Every code panel is read off disk at record time and sliced by *anchor text*
 * rather than line numbers, so the video cannot drift from the repository and
 * an edit that moves a function does not silently shift the frame onto the
 * wrong code. A missing anchor is reported at the end rather than crashing the
 * run, so one stale anchor does not cost a full re-record.
 */

import { chromium } from "playwright";
import { readFileSync, readdirSync, mkdirSync, renameSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.DEMO_ROOT ? resolve(process.env.DEMO_ROOT) : resolve(HERE, "..");

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 ? process.argv[i + 1] : fallback;
};

const OUT = resolve(ROOT, arg("out", "demo/out-tutorial"));
const DECK = `file://${join(ROOT, "demo", "demo-page.html")}`;
const SIZE = { width: 1600, height: 900 };
const MAX_LINES = 30;

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const missing = [];

/** Slice a real file by anchor text. */
function readSlice(file, { start, lines, before = 0 }) {
  const path = join(ROOT, file);
  if (!existsSync(path)) {
    missing.push(`${file} (file not found)`);
    return { lines: ["(file not found)"], startLine: 1 };
  }
  const all = readFileSync(path, "utf8").replace(/\s+$/, "").split("\n");

  let from = 0;
  if (start) {
    const i = all.findIndex((l) => l.includes(start));
    if (i === -1) missing.push(`${file} :: ${JSON.stringify(start)}`);
    else from = Math.max(0, i - before);
  }
  const count = Math.min(lines ?? MAX_LINES, MAX_LINES);
  return { lines: all.slice(from, from + count), startLine: from + 1 };
}

function focusLines(slice, focusText) {
  if (!focusText || !focusText.length) return [];
  const hits = [];
  slice.lines.forEach((l, i) => {
    if (focusText.some((f) => l.includes(f))) hits.push(slice.startLine + i);
  });
  if (!hits.length) missing.push(`focus ${JSON.stringify(focusText)}`);
  return hits;
}

/* ===================================================================
   The tutorial. Ordered so someone could rebuild the project from
   scratch by following it: the application first, then how it is
   packaged, then each deployment target, then the infrastructure that
   makes the cloud targets interchangeable, then the automation.
   =================================================================== */

const STEPS = [
  { t: "title", hold: 4600,
    h1: "Building this from scratch",
    h2: "A guided walk through every component, in the order you would write them",
    chips: ["<b>1</b> the application", "<b>2</b> packaging", "<b>3</b> three deployments", "<b>4</b> Terraform", "<b>5</b> automation"],
    cap: "Follow this end to end and you could rebuild the project without the repository in front of you." },

  { t: "grid", hold: 7000, n: "00", title: "What you are going to build", sub: "Five layers, each one depending only on the one above it",
    groups: [
      { title: "1 · Application", tone: "app", items: [
        { name: "FastAPI backend", note: "async SQLAlchemy + Alembic" },
        { name: "React frontend", note: "Vite, TypeScript" },
        { name: "PostgreSQL", note: "one table" },
        { name: "nginx", note: "serves the SPA, proxies /api" } ] },
      { title: "2 · Packaging", tone: "cd", items: [
        { name: "Two Dockerfiles", note: "multi-stage, non-root" },
        { name: "docker-compose.yml", note: "the inner loop" },
        { name: "Helm chart", note: "provider-blind" } ] },
      { title: "3 · Infrastructure", tone: "infra", items: [
        { name: "Role modules", note: "network / k8s / database" },
        { name: "Two stacks", note: "aws, gcp" },
        { name: "Platform contract", note: "the seam" } ] },
      { title: "4 · Automation", tone: "ai", items: [
        { name: "Scripts", note: "deploy, values, minikube" },
        { name: "GitHub Actions", note: "4 workflows" },
        { name: "aiops", note: "policy engine + gate" } ] },
    ],
    cap: "Build them in this order. Each layer only needs the one above it to exist, so you can run and test as you go." },

  /* ---------------------------------------------------- 1. application */
  { t: "code", n: "01", title: "Configuration", sub: "Everything from the environment, so one image runs anywhere",
    file: "backend/app/config.py", start: "class Settings", lines: 26,
    focus: ["database_url", "cloud:", "environment:"],
    cap: "Start here. No cloud SDK and no provider metadata lookups — that single decision is what lets the same image run on Compose, minikube, EKS and GKE." },

  { t: "code", n: "02", title: "The database session", sub: "One async engine, created and disposed with the app",
    file: "backend/app/db/session.py", start: "def _build_engine", lines: 24,
    focus: ["pool_pre_ping", "sqlite", "async_sessionmaker"],
    cap: "The SQLite branch is not decoration: it is what lets the test suite run the real application code with no database container." },

  { t: "code", n: "03", title: "The model", sub: "One table, and a deliberate note about who owns the schema",
    file: "backend/app/models.py", start: "class Idea", lines: 14,
    focus: ["__tablename__", "server_default"],
    cap: "The schema is owned by Alembic, not by <code>create_all</code>. Writing that down early stops the two drifting apart later." },

  { t: "code", n: "04", title: "Validation at the boundary", sub: "Pydantic schemas are the contract with the outside world",
    file: "backend/app/schemas.py", start: "class IdeaCreate", lines: 16,
    focus: ["min_length", "def _strip", "raise ValueError"],
    cap: "Trim first, then reject what is empty. A whitespace-only idea is a 422 before it ever reaches the database." },

  { t: "code", n: "05", title: "The API", sub: "Two endpoints, and that is the whole product surface",
    file: "backend/app/routers/ideas.py", start: "@router.get", lines: 26,
    focus: ["order_by", "status_code=status.HTTP_201_CREATED", "await session.commit"],
    cap: "Newest first, a bounded limit, and 201 on create. Small enough that the interesting engineering is clearly everywhere else." },

  { t: "code", n: "06", title: "Health: the three-probe split", sub: "The most consequential twenty lines in the backend",
    file: "backend/app/routers/health.py", start: "@router.get(\"/healthz\"", lines: 30,
    focus: ["/healthz", "/readyz", "SELECT 1 FROM ideas", "not-checked"],
    cap: "Liveness never touches the database, so a database blip cannot restart every pod at once. Readiness queries the real table, so a pod that failed to migrate can never report ready." },

  { t: "code", n: "07", title: "The app factory", sub: "Wiring, CORS and the metrics the release gate will read",
    file: "backend/app/main.py", start: "def create_app", lines: 22,
    focus: ["lifespan", "Instrumentator", "/metrics"],
    cap: "Exposing <code>/metrics</code> here is what makes the AI release gate possible later — it reads the 5xx rate straight from this endpoint." },

  { t: "code", n: "08", title: "Migrations under concurrency", sub: "The advisory lock, and the bug that hid inside it",
    file: "backend/migrations/env.py", start: "def _do_run", lines: 30,
    focus: ["pg_advisory_lock", "connection.commit()", "pg_advisory_unlock"],
    cap: "Every replica runs this on startup. A session-level lock serialises them — and the explicit commits are load-bearing: without them the lock's implicit transaction swallowed the migration and it silently applied nothing." },

  { t: "code", n: "09", title: "The first migration", sub: "Plain Alembic, deliberately boring",
    file: "backend/migrations/versions/0001_create_ideas.py", start: "def upgrade", lines: 18,
    focus: ["create_table", "create_index"],
    cap: "Index the column you sort by. At this size it does not matter; establishing the habit in migration one does." },

  { t: "code", n: "10", title: "The backend image", sub: "Multi-stage, non-root, and a healthcheck that actually works",
    file: "backend/Dockerfile", start: "FROM python:3.12-slim AS runtime", lines: 26,
    focus: ["useradd", "USER 10001", "127.0.0.1"],
    cap: "Wheels are built in a throwaway stage so no compiler ships. And the healthcheck says 127.0.0.1, not localhost — in some images localhost resolves to ::1 first and the check fails against a perfectly healthy service." },

  { t: "code", n: "11", title: "The frontend's API client", sub: "One decision here removes a whole class of deployment problem",
    file: "frontend/src/api.ts", start: "async function request", lines: 24,
    focus: ["/api/ideas", "ApiError", "res.ok"],
    cap: "Every path is relative. nginx owns the /api proxy in every image, so there is no build-time API URL and no CORS — the bundle CI tested is the bundle production runs." },

  { t: "code", n: "12", title: "nginx configuration", sub: "Rendered at container start, and a header trap worth knowing",
    file: "frontend/nginx.conf.template", start: "map $uri $cache_control", lines: 28,
    focus: ["map $uri", "add_header", "BACKEND_HOST"],
    cap: "Cache-Control is computed by a map rather than set inside each location, because an add_header in an inner block <b>replaces</b> every inherited header — which silently dropped the security headers on exactly the pages that serve HTML." },

  { t: "code", n: "13", title: "The frontend image", sub: "Why its build context is the repository root",
    file: "frontend/Dockerfile", start: "FROM nginxinc/nginx-unprivileged", lines: 22,
    focus: ["COPY docs/", "USER 101", "BACKEND_HOST"],
    cap: "Docker cannot read above its context, and the image ships the project documentation — so the context is the repo root, trimmed by a root .dockerignore, rather than duplicating the markdown into frontend/." },

  /* ------------------------------------------------------ 2. compose */
  { t: "code", n: "14", title: "Deployment one: Docker Compose", sub: "The inner loop, shaped like the cluster on purpose",
    file: "docker-compose.yml", start: "  migrate:", lines: 28,
    focus: ["migrate:", "condition: service_healthy", "RUN_MIGRATIONS"],
    cap: "The one-shot migrate service runs to completion before the backend starts — exactly what the init container does in Kubernetes. Mirroring the topology is what stops the local and cluster paths drifting." },

  { t: "term", n: "15", title: "Running it locally", sub: "Two commands and a working stack",
    termTitle: "docker compose", key: "02-ideas",
    cap: "<code>docker compose up --build -d</code>, then the app is on :8080 and the API on :8000. This is the loop you develop in." },

  /* -------------------------------------------------------- 3. helm */
  { t: "code", n: "16", title: "The Helm chart's values", sub: "Everything cloud-shaped arrives under one key",
    file: "deploy/helm/idea-board/values.yaml", start: "platform:", lines: 30,
    focus: ["platform:", "secretBackend", "serviceAccountAnnotations"],
    cap: "This whole block is generated from Terraform, never hand-edited. Below it sits the sizing the AI policy engine is allowed to propose." },

  { t: "code", n: "17", title: "Chart helpers", sub: "Where the registry and ingress differences are absorbed",
    file: "deploy/helm/idea-board/templates/_helpers.tpl", start: "idea-board.image", before: 4, lines: 26,
    focus: ["registry.host", "ingressAnnotations", "alb", "gce"],
    cap: "The image reference is assembled from the contract, so the same template resolves to an ECR URI or an Artifact Registry URI untouched. Ingress annotations are the one place a cloud name legitimately appears." },

  { t: "code", n: "18", title: "The backend workload", sub: "Probes, spread and the migration init container",
    file: "deploy/helm/idea-board/templates/backend.yaml", start: "topologySpreadConstraints", lines: 30,
    focus: ["topologySpreadConstraints", "maxSkew", "ScheduleAnyway"],
    cap: "Spread across zones with ScheduleAnyway — DoNotSchedule would turn a zone outage into unschedulable pods, which is precisely when you want them to run somewhere." },

  { t: "code", n: "19", title: "Probes in the manifest", sub: "The three-way split, expressed to Kubernetes",
    file: "deploy/helm/idea-board/templates/backend.yaml", start: "startupProbe", lines: 22,
    focus: ["startupProbe", "livenessProbe", "readinessProbe"],
    cap: "Startup absorbs a slow boot so liveness can stay tight. Readiness hits /readyz and therefore the real table. Three probes, three jobs — one probe doing all three is how you get restart storms." },

  { t: "code", n: "20", title: "Rollout safety", sub: "How a bad release fails to reach anyone",
    file: "deploy/helm/idea-board/templates/backend.yaml", start: "strategy:", lines: 12,
    focus: ["maxUnavailable: 0", "maxSurge"],
    cap: "maxUnavailable: 0 means a new pod must pass readiness before an old one is removed, so capacity never dips mid-deploy." },

  { t: "code", n: "21", title: "Secrets, in-cluster", sub: "The one provider-specific stanza in the whole delivery layer",
    file: "deploy/helm/idea-board/templates/externalsecret.yaml", start: "provider:", lines: 28,
    focus: ["secretsmanager", "secretmanager", "fail", "DATABASE_URL"],
    cap: "Two branches for two secret stores, and an explicit fail for anything else. External Secrets assembles DATABASE_URL in-cluster, so the password never appears in Terraform state, CI logs or a values file." },

  { t: "code", n: "22", title: "Network policy", sub: "Default deny, then only the paths the app needs",
    file: "deploy/helm/idea-board/templates/networkpolicy.yaml", start: "podSelector: {}", before: 6, lines: 24,
    focus: ["podSelector: {}", "policyTypes"],
    cap: "An empty podSelector with both policy types is the default-deny. Everything after it is an explicit allowance — written with pod selectors and ports so it works on any CNI that enforces policy." },

  /* ---------------------------------------------------- 4. minikube */
  { t: "code", n: "23", title: "Deployment two: minikube", sub: "Real Kubernetes with no cloud account",
    file: "scripts/minikube-up.sh", start: "log \"building images", before: 2, lines: 26,
    focus: ["minikube docker-env", "rollout restart", "--atomic"],
    cap: "Build straight into minikube's Docker daemon so there is no registry. The rollout restart is needed because the :local tag is mutable — an unchanged release leaves the pod spec identical and Helm has nothing to roll." },

  { t: "code", n: "24", title: "The local database", sub: "And a probe lesson that cost eleven restarts",
    file: "deploy/local/postgres.yaml", start: "readinessProbe", before: 6, lines: 30,
    focus: ["timeoutSeconds", "failureThreshold", "livenessProbe"],
    cap: "Set timeoutSeconds explicitly on exec probes: the default is one second, pg_isready has to fork a process, and three slow probes had the kubelet restarting a completely healthy database every sixty seconds." },

  /* --------------------------------------------------- 5. terraform */
  { t: "grid", hold: 7000, n: "25", title: "Deployment three: the cloud", sub: "How the Terraform directory is laid out, and why",
    groups: [
      { title: "modules/ — role, not cloud", tone: "infra", items: [
        { name: "platform-contract", note: "the normalised output" },
        { name: "aws-network / gcp-network", note: "VPC, subnets, NAT" },
        { name: "aws-kubernetes / gcp-kubernetes", note: "EKS / GKE + registry" },
        { name: "aws-database / gcp-database", note: "RDS / Cloud SQL" } ] },
      { title: "stacks/ — one root per cloud", tone: "cd", items: [
        { name: "stacks/aws", note: "wires 3 modules + IRSA" },
        { name: "stacks/gcp", note: "wires 3 modules + WI" },
        { name: "identical variables", note: "except project_id" },
        { name: "partial backends", note: "bucket passed at init" } ] },
      { title: "envs/ — the only per-env file", tone: "app", items: [
        { name: "aws-dev.tfvars", note: "cost-optimised" },
        { name: "gcp-dev.tfvars", note: "same, two lines differ" },
        { name: "aws-prod.tfvars", note: "high availability" },
        { name: "gcp-prod.tfvars", note: "same intent" } ] },
      { title: "What never appears", tone: "ai", items: [
        { name: "No cloud name downstream", note: "chart, scripts, CI" },
        { name: "No password in state", note: "only a reference" },
        { name: "No static credential", note: "OIDC federation" },
        { name: "No machine types in envs", note: "t-shirt sizes" } ] },
    ],
    cap: "Modules are organised by <b>role</b>, implemented once per cloud. That is what makes adding a third provider a matter of satisfying three interfaces." },

  { t: "code", n: "26", title: "The platform contract", sub: "The single most important file in the repository",
    file: "infra/terraform/modules/platform-contract/outputs.tf", start: "output \"platform\"", lines: 22,
    focus: ["schema_version", "account_id", "service_account_annotations"],
    cap: "Every cloud fills this same shape, and it is versioned. The cluster and registry objects arrive from the stack and carry opaque command strings the deploy script simply executes — which is exactly why that script has no provider branching." },

  { t: "code", n: "27", title: "The variable contract", sub: "Identical in both stacks, and that is the point",
    file: "infra/terraform/stacks/aws/variables.tf", start: "variable \"node_size\"", before: 6, lines: 28,
    focus: ["node_size", "high_availability", "cost_optimized"],
    cap: "Cloud-neutral intent: t-shirt sizes and boolean posture, never a machine type. The GCP stack's file is this one plus project_id." },

  { t: "code", n: "28", title: "Sizing", sub: "Where a t-shirt size becomes a machine type",
    file: "infra/terraform/stacks/aws/sizing.tf", start: "node_instance_types", before: 2, lines: 26,
    focus: ["medium", "use_spot", "db_instance_class"],
    cap: "One lookup table per stack, matched on vCPU and RAM so a medium environment behaves the same on either cloud. Change this file and every environment moves together." },

  { t: "code", n: "29", title: "Wiring a stack", sub: "Three modules, an identity, and the contract",
    file: "infra/terraform/stacks/aws/main.tf", start: "module \"kubernetes\"", lines: 28,
    focus: ["module \"kubernetes\"", "module \"database\"", "module \"platform\""],
    cap: "The root is deliberately thin. All it does is pass cloud-neutral variables into three role modules and funnel the results into the contract." },

  { t: "code", n: "30", title: "Pod identity", sub: "IRSA on AWS — the same idea, a different noun on GCP",
    file: "infra/terraform/stacks/aws/main.tf", start: "aws_iam_role\" \"app", before: 4, lines: 26,
    focus: ["assume_role_policy", "sub", "secretsmanager:GetSecretValue"],
    cap: "The trust policy binds one Kubernetes service account to one IAM role. The pod then reads exactly one secret — no static key exists anywhere in this design." },

  { t: "term", n: "31", title: "Switching clouds", sub: "The entire difference between an AWS and a GCP environment",
    termTitle: "diff aws-dev.tfvars gcp-dev.tfvars", key: "03-tfvars",
    cap: "Two lines: a region and GCP's project id. Every sizing, availability and budget knob is identical because they are all cloud-neutral." },

  { t: "table", n: "32", title: "What actually changes", sub: "Same chart, same values file shape, different contract contents",
    headers: ["", "AWS", "GCP"],
    rows: [
      { cells: ["Cluster", "EKS", "GKE"] },
      { cells: ["Database", "RDS Postgres", "Cloud SQL"] },
      { cells: ["Registry", "ECR", "Artifact Registry"] },
      { cells: ["Identity", "IRSA (role ARN)", "Workload Identity (SA email)"] },
      { cells: ["Secret store", "Secrets Manager", "Secret Manager"] },
      { cells: ["Ingress class", "alb", "gce"] },
      { cells: ["<b>Helm chart</b>", "<b>identical</b>", "<b>identical</b>"] },
      { cells: ["<b>Deploy command</b>", "<b>identical</b>", "<b>identical</b>"] },
    ],
    note: "Everything in the top block is produced by the stack and normalised into the contract. Everything in the bottom block never learns which cloud it is on.",
    cap: "This table is the whole cloud-agnostic claim: the differences are real, and they stop at the contract." },

  /* ----------------------------------------------------- 6. scripts */
  { t: "code", n: "33", title: "The seam, in one mapping", sub: "Terraform output to Helm values",
    file: "scripts/platform-values.sh", start: "jq '{", before: 4, lines: 28,
    focus: ["schema_version", "gcpProjectId", "secretBackend"],
    cap: "Thirty lines of jq are the entire boundary between infrastructure and delivery. It also refuses to run against a contract schema it does not speak." },

  { t: "code", n: "34", title: "The deploy script", sub: "Read it looking for provider branching — there is none",
    file: "scripts/deploy.sh", start: "PLATFORM=", before: 2, lines: 28,
    focus: ["kubeconfig_command", "platform-values.sh", "--atomic"],
    cap: "It authenticates by executing the command the contract handed it. That one line is why the same script deploys to EKS and GKE without knowing the difference." },

  /* ---------------------------------------------------- 7. ai layer */
  { t: "code", n: "35", title: "The AI layer: the schema", sub: "Everything the model is allowed to emit",
    file: "ai/aiops/models.py", start: "class InfraProposal", lines: 28,
    focus: ["extra=\"forbid\"", "ge=1", "rationale"],
    cap: "A narrow, typed surface. The model picks from the same knobs a human would set in a tfvars file — it cannot invent a field or name a resource." },

  { t: "code", n: "36", title: "The policy engine", sub: "The half that decides",
    file: "ai/aiops/policy.py", start: "def evaluate", lines: 28,
    focus: ["def evaluate", "prod = intent.is_production_grade", "Severity.violation"],
    cap: "A pure function: proposal in, findings out. No cloud calls, no model, fully unit-testable — which is why ninety tests cover this logic without touching the API." },

  { t: "code", n: "37", title: "A rule that caught a real outage", sub: "The database connection ceiling",
    file: "ai/aiops/policy.py", start: "capacity.db_connections", before: 8, lines: 24,
    focus: ["capacity.db_connections", "peak_replicas", "safe_replicas"],
    cap: "Each replica opens ten connections, so the autoscaler could have scaled production into connection exhaustion. The rule checks the <b>maximum</b>, because the failure only appears under the load that triggers scale-up." },

  { t: "code", n: "38", title: "The release gate: triage", sub: "Deterministic rules run first, and usually finish the job",
    file: "ai/aiops/gate.py", start: "def triage", lines: 28,
    focus: ["crash_loop", "Triage.hard_fail", "Triage.clean"],
    cap: "A crash loop is a rollback and a clean rollout is a pass, neither costing an API call. The model is consulted only for what is left over." },

  { t: "code", n: "39", title: "The release gate: override", sub: "Hard signals beat the model, in both directions",
    file: "ai/aiops/gate.py", start: "def apply_overrides", lines: 28,
    focus: ["hard_fail_signal", "grounded", "ROLLBACK_CONFIDENCE_FLOOR"],
    cap: "It cannot call a crash loop healthy, a low-confidence rollback is downgraded to an alert, and findings with no cited excerpt are dropped — because an unsupported claim is what a hallucination looks like." },

  { t: "code", n: "40", title: "ChatOps without a shell", sub: "The model selects operations; the catalogue renders argv",
    file: "ai/aiops/commands.py", start: "class Operation", lines: 28,
    focus: ["def build", "validator(arguments[key])", "destructive"],
    cap: "Every argument goes through a validator and the result is an argv list, never a shell string. The worst a confused model can do is pick a wrong allowlisted operation with valid parameters." },

  { t: "code", n: "41", title: "Talking to the model", sub: "Structured outputs, refusals, and one recoverable error",
    file: "ai/aiops/llm.py", start: "response = client.beta.messages.create", before: 3, lines: 28,
    focus: ["json_schema", "stop_reason", "fallbacks", "LlmUnavailable"],
    cap: "A refusal arrives as a normal 200, so stop_reason is checked before reading content. Every failure becomes one exception that every caller knows how to degrade from." },

  /* --------------------------------------------------------- 8. CI */
  { t: "code", n: "42", title: "Continuous integration", sub: "What runs on every pull request",
    file: ".github/workflows/ci.yml", start: "jobs:", lines: 28,
    focus: ["jobs:", "runs-on"],
    cap: "Tests, lint, terraform validate on both stacks, helm lint against three contract fixtures, and both image builds. No secrets required, so it runs on forks." },

  { t: "code", n: "43", title: "Deploying from CI", sub: "OIDC federation, then the same script you run by hand",
    file: ".github/workflows/deploy.yml", start: "permissions:", lines: 26,
    focus: ["id-token: write", "role-to-assume", "matrix"],
    cap: "<code>id-token: write</code> is what lets GitHub exchange a short-lived token for a cloud role. There is no static credential in this repository." },

  /* ------------------------------------------------------ 9. rebuild */
  { t: "table", n: "44", title: "Rebuilding it from scratch", sub: "The order that keeps you running something at every step",
    headers: ["#", "Build", "You can run it when"],
    rows: [
      { cells: ["1", "FastAPI app + Alembic migration", "pytest passes against SQLite"] },
      { cells: ["2", "Dockerfiles + docker-compose.yml", "the stack answers on :8080"] },
      { cells: ["3", "React frontend behind nginx", "posting an idea works end to end"] },
      { cells: ["4", "Helm chart + minikube values", "it runs on real Kubernetes"] },
      { cells: ["5", "platform-contract module", "the shape is agreed before any cloud"] },
      { cells: ["6", "One cloud's three role modules", "terraform validate passes"] },
      { cells: ["7", "platform-values.sh + deploy.sh", "you can deploy to that cloud"] },
      { cells: ["8", "The second cloud", "the two-line tfvars diff holds"] },
      { cells: ["9", "aiops policy engine, then the gate", "tests pass with no API key"] },
      { cells: ["10", "GitHub Actions", "a push deploys and is judged"] },
    ],
    note: "Build the contract (step 5) <b>before</b> the second cloud, not after. Retrofitting a contract onto two finished stacks is far harder than agreeing the shape up front.",
    cap: "Each step leaves you something you can actually run, which is how you catch the bugs that only appear when it is deployed." },

  { t: "title", hold: 6000,
    h1: "That is the whole system",
    h2: "Application, packaging, three deployment targets, the contract that makes two clouds interchangeable, and the automation on top",
    chips: ["<b>~13k</b> lines", "<b>90</b> tests", "<b>2</b> clouds", "<b>3</b> targets", "<b>8</b> docs"],
    cap: "Every file shown was read from the repository as this was recorded, so what you have just watched is the code as it actually stands." },
];

/* =================================================================== */

function loadCaptures(dir) {
  const data = {};
  if (!existsSync(dir)) return data;
  for (const f of readdirSync(dir).filter((x) => x.endsWith(".txt")).sort()) {
    data[f.replace(/\.txt$/, "")] = readFileSync(join(dir, f), "utf8").replace(/\s+$/, "").split("\n");
  }
  return data;
}

/** --dry resolves every slice and reports bad anchors without recording. */
function dryRun() {
  for (const s of STEPS) {
    if (s.t !== "code") continue;
    const slice = readSlice(s.file, { start: s.start, lines: s.lines, before: s.before });
    focusLines(slice, s.focus);
  }
  console.log(`checked ${STEPS.filter((s) => s.t === "code").length} code panels`);
  if (missing.length) {
    console.log(`\n${missing.length} problem(s):`);
    for (const m of missing) console.log("  " + m);
    process.exitCode = 1;
  } else {
    console.log("every anchor and focus matched");
  }
}

async function main() {
  if (process.argv.includes("--dry")) return dryRun();
  mkdirSync(OUT, { recursive: true });
  const captures = loadCaptures(resolve(ROOT, "demo/captures"));

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: SIZE,
    deviceScaleFactor: 2,
    recordVideo: { dir: OUT, size: SIZE },
  });
  const page = await context.newPage();

  let n = 0;
  const total = STEPS.length;
  const step = () => `${String(++n).padStart(2, "0")} / ${total}`;

  for (const s of STEPS) {
    await page.goto(DECK);
    await page.evaluate((d) => { window.__demo.data = d; }, captures);

    if (s.t === "title") {
      await page.evaluate(([a, b, c]) => window.__demo.title(a, b, c), [s.h1, s.h2, s.chips]);
    } else if (s.t === "grid") {
      await page.evaluate(([a, b, c, g]) => window.__demo.grid(a, b, c, g), [s.n, s.title, s.sub, s.groups]);
    } else if (s.t === "table") {
      await page.evaluate(([a, b, c, h, r, note]) => window.__demo.table(a, b, c, h, r, note),
        [s.n, s.title, s.sub, s.headers, s.rows, s.note]);
    } else if (s.t === "term") {
      await page.evaluate(([a, b, c, t]) => window.__demo.section(a, b, c, t), [s.n, s.title, s.sub, s.termTitle]);
      await page.evaluate((k) => window.__demo.type(k, 55), s.key);
    } else if (s.t === "code") {
      const slice = readSlice(s.file, { start: s.start, lines: s.lines, before: s.before });
      const focus = focusLines(slice, s.focus);
      await page.evaluate(([a, b, c, path, lines, startLine, f]) =>
        window.__demo.code(a, b, c, path, lines, startLine, f),
        [s.n, s.title, s.sub, s.file, slice.lines, slice.startLine, focus]);
    }

    await page.evaluate(([c, st]) => window.__demo.setCaption(c, st), [s.cap, step()]);

    // Code panels need reading time proportional to how much is on screen.
    const hold = s.hold ?? (s.t === "code" ? 7200 : s.t === "term" ? 6000 : 6000);
    await wait(hold);
  }

  await context.close();
  await browser.close();

  const produced = readdirSync(OUT).filter((f) => f.endsWith(".webm"));
  const newest = produced.map((f) => join(OUT, f)).sort()[produced.length - 1];
  const target = join(OUT, "idea-board-tutorial.webm");
  if (newest && newest !== target) renameSync(newest, target);

  console.log(`\nrecorded ${n} steps: ${target}`);
  if (missing.length) {
    console.log(`\n${missing.length} anchor(s) did not match — those panels show the top of the file:`);
    for (const m of missing) console.log("  " + m);
  } else {
    console.log("every anchor matched");
  }
}

main().catch((err) => { console.error(err); process.exit(1); });
