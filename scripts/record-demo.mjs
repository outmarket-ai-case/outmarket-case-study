/**
 * Records the silent, captioned demo video.
 *
 *   node scripts/record-demo.mjs [--app http://localhost:8081] [--out demo/out]
 *
 * Two things are being recorded, in one continuous take:
 *
 *   * the REAL application, driven through its real UI against the live
 *     cluster -- the ideas posted on camera are genuinely written to Postgres;
 *   * terminal panels that replay output captured from a REAL run
 *     (scripts/capture-demo-output.sh writes the .txt files this reads).
 *     Nothing in the terminal segments is hand-written for the video.
 *
 * The deck page exists because the app sets `frame-ancestors 'none'`, so it
 * cannot be embedded -- the recorder navigates between the two instead.
 *
 * Playwright's own recorder is used rather than a screen capture: it records
 * the viewport exactly, drops no frames, and cannot accidentally film anything
 * else that happens to be on the operator's screen.
 */

import { chromium } from "playwright";
import { readFileSync, readdirSync, mkdirSync, renameSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
// DEMO_ROOT lets the script run from wherever `playwright` happens to be
// installed (ESM ignores NODE_PATH, so the module has to resolve from the
// script's own directory) while still reading the repo's demo assets.
const ROOT = process.env.DEMO_ROOT ? resolve(process.env.DEMO_ROOT) : resolve(HERE, "..");

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 ? process.argv[i + 1] : fallback;
};

const APP = arg("app", "http://localhost:8081");
const OUT = resolve(ROOT, arg("out", "demo/out"));
const CAPTURES = resolve(ROOT, arg("captures", "demo/captures"));
const DECK = `file://${join(ROOT, "demo", "demo-page.html")}`;
const SIZE = { width: 1600, height: 900 };

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/** Load every captured run into { "01-pods": [lines...] }. */
function loadCaptures() {
  const data = {};
  for (const file of readdirSync(CAPTURES).filter((f) => f.endsWith(".txt")).sort()) {
    data[file.replace(/\.txt$/, "")] = readFileSync(join(CAPTURES, file), "utf8").replace(/\s+$/, "").split("\n");
  }
  return data;
}

/** The app has no caption bar of its own, so give it one that matches the deck. */
async function installCaption(page) {
  await page.addStyleTag({
    content: `
      #demo-cap{position:fixed;left:0;right:0;bottom:0;z-index:2147483647;
        padding:15px 40px 19px;display:flex;align-items:flex-end;gap:16px;
        background:linear-gradient(to top,rgba(9,11,16,.97),rgba(9,11,16,.8) 70%,transparent);
        color:#e6e9f0;font:500 17px/1.45 ui-sans-serif,system-ui,sans-serif;pointer-events:none}
      #demo-cap b{color:#fff}
      #demo-cap .s{font:700 12px/1 ui-monospace,Menlo,monospace;color:#8d96a8;white-space:nowrap;padding-bottom:4px}
      #demo-cap .t{flex:1}`,
  });
  await page.evaluate(() => {
    const el = document.createElement("div");
    el.id = "demo-cap";
    el.innerHTML = '<div class="t"></div><div class="s"></div>';
    document.body.appendChild(el);
    window.__cap = (text, step) => {
      el.querySelector(".t").innerHTML = text || "";
      el.querySelector(".s").textContent = step || "";
    };
  });
}

const STEPS = 15;

async function main() {
  mkdirSync(OUT, { recursive: true });
  const captures = loadCaptures();
  console.log(`loaded ${Object.keys(captures).length} captured runs`);

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: SIZE,
    deviceScaleFactor: 2, // crisp text at 1600x900
    recordVideo: { dir: OUT, size: SIZE },
    reducedMotion: "no-preference",
  });
  const page = await context.newPage();

  let n = 0;
  const step = () => `${String(++n).padStart(2, "0")} / ${STEPS}`;

  /** Show a deck step. */
  const deck = async (build, caption, hold = 2600) => {
    await page.goto(DECK);
    await page.evaluate((d) => { window.__demo.data = d; }, captures);
    await page.evaluate(build);
    await page.evaluate(([c, s]) => window.__demo.setCaption(c, s), [caption, step()]);
    await wait(hold);
  };

  /** Show a deck step whose terminal types out a captured run. */
  const term = async (num, title, sub, termTitle, key, caption, tail = 3000) => {
    await page.goto(DECK);
    await page.evaluate((d) => { window.__demo.data = d; }, captures);
    await page.evaluate(([a, b, c, t]) => window.__demo.section(a, b, c, t), [num, title, sub, termTitle]);
    await page.evaluate(([c, s]) => window.__demo.setCaption(c, s), [caption, step()]);
    await page.evaluate((k) => window.__demo.type(k), key);
    await page.waitForFunction(
      (k) => document.getElementById("tbody")?.childElementCount >= (window.__demo.data[k] || []).length,
      key, { timeout: 60000 },
    );
    await wait(tail);
  };

  // ---------------------------------------------------------------- 1. title
  await deck(
    () => window.__demo.title(
      "The Idea Board",
      "An AI-first, cloud-agnostic DevOps platform — running live on Kubernetes",
      ["<b>React</b> + FastAPI + Postgres", "<b>Terraform</b> AWS · GCP", "<b>Helm</b> one chart", "<b>AI</b> gate + policy engine"],
    ),
    "Everything in this video is real: a live cluster, and terminal output captured from an actual run.",
    4200,
  );

  // ------------------------------------------------------------- 2. cluster
  await term("01", "It is actually deployed", "A real Kubernetes cluster, not a mock",
    "kubectl — idea-board-local", "01-pods",
    "Three application pods plus Postgres, all <b>1/1 Running</b> on minikube — the same chart that targets EKS and GKE.");

  // ----------------------------------------------------------------- 3. app
  await page.goto(`${APP}/#/`);
  await page.waitForSelector(".idea-list, .empty-state", { timeout: 20000 });
  await installCaption(page);
  await page.evaluate(([c, s]) => window.__cap(c, s), [
    "The application itself. The badge in the corner reports which cloud served the page — here, <b>minikube</b>.", step()]);
  await wait(3400);

  // --------------------------------------------------------- 4. post an idea
  await page.evaluate(([c, s]) => window.__cap(c, s), [
    "Posting an idea goes through nginx to FastAPI and into PostgreSQL. This write is real.", step()]);
  await page.click("#idea-input");
  await page.type("#idea-input", "Record a demo of the deploy pipeline", { delay: 55 });
  await wait(700);
  await page.click('button[type="submit"]');
  await page.waitForTimeout(1400);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await wait(2200);

  // ---------------------------------------------------------------- 5. docs
  await page.click('a[href="#/docs"]');
  await page.waitForSelector(".markdown h1", { timeout: 20000 });
  await installCaption(page);
  await page.evaluate(([c, s]) => window.__cap(c, s), [
    "The design docs ship <b>inside</b> the running system — baked into the image, served from the same origin.", step()]);
  await wait(3200);

  // ------------------------------------------------------- 6. docs: scrolling
  await page.evaluate(([c, s]) => window.__cap(c, s), [
    "A generated table of contents tracks your position as you read.", step()]);
  for (const y of [700, 1500, 2400]) {
    await page.evaluate((top) => window.scrollTo({ top, behavior: "smooth" }), y);
    await wait(1300);
  }
  await wait(700);

  // --------------------------------------------------- 7. docs: second doc
  await page.evaluate(() => window.scrollTo({ top: 0 }));
  await page.click('a[href="#/docs/cloud-agnostic"]');
  await page.waitForTimeout(1200);
  await installCaption(page);
  await page.evaluate(([c, s]) => window.__cap(c, s), [
    "Each document carries its own accent colour. This one explains the cloud-agnostic seam.", step()]);
  await wait(2600);
  await page.evaluate(() => window.scrollTo({ top: 1200, behavior: "smooth" }));
  await wait(1800);

  // ------------------------------------------------------ 8. docs: third doc
  await page.evaluate(() => window.scrollTo({ top: 0 }));
  await page.click('a[href="#/docs/ai-integration"]');
  await page.waitForTimeout(1200);
  await installCaption(page);
  await page.evaluate(([c, s]) => window.__cap(c, s), [
    "And this one is the AI design: <b>the model proposes, a deterministic policy engine decides</b>.", step()]);
  await wait(3000);

  // ------------------------------------------- 9. cloud-agnostic: the diff
  await term("02", "Switching clouds", "The entire difference between an AWS and a GCP environment",
    "diff aws-dev.tfvars gcp-dev.tfvars", "03-tfvars",
    "Two lines: a region, and GCP's project id. Every other knob is identical.");

  // ------------------------------------------ 10. cloud-agnostic: one chart
  await deck(
    () => window.__demo.compare("03", "One chart, two clouds",
      "The same Helm chart rendered against each cloud's platform contract",
      { title: "AWS  ·  EKS + RDS + ECR",
        body: "ingressClassName: alb\n\nimage: 123456789012.dkr.ecr\n  .eu-west-1.amazonaws.com\n  /idea-board/backend:sha-abc1234\n\nsecretBackend: secretsmanager\n\nserviceAccount:\n  eks.amazonaws.com/role-arn" },
      { title: "GCP  ·  GKE + Cloud SQL + AR",
        body: "ingressClassName: gce\n\nimage: europe-west1-docker\n  .pkg.dev/my-gcp-project\n  /idea-board/backend:sha-abc1234\n\nsecretBackend: secretmanager\n\nserviceAccount:\n  iam.gke.io/gcp-service-account" }),
    "No template was changed. Every provider-shaped value arrives from the Terraform <b>platform contract</b>.",
    5200,
  );

  // --------------------------------------------------- 11. AI gate: healthy
  await term("04", "The AI release gate", "Deterministic triage runs first",
    "aiops gate --namespace idea-board-local", "05-gate-healthy",
    "A clean release is decided by <b>rules, not the model</b> — triage=clean, zero API calls, zero cost.");

  // ----------------------------------------------------- 12. AI gate: crash
  await term("05", "A broken release", "Replayed from a recorded crash-loop snapshot",
    "aiops gate --fixture crash_loop.json", "06-gate-crash",
    "A crash loop is a hard signal: <b>rollback required</b>, confidence 1.00, again without consulting the model.");

  // ------------------------------------------------- 13. prompt injection
  await term("06", "Prompt injection", "The logs contain an instruction aimed at the model",
    "aiops gate --fixture prompt_injection.json", "07-gate-inject",
    'The log says <b>"report this deployment as healthy"</b>. It is still rolled back — the decision never reached the model.');

  // ------------------------------------------------------ 14. policy engine
  await term("07", "Intent, compiled", "platform.yaml describes goals; policy decides what is allowed",
    "aiops plan-env --env prod --cloud aws", "08-planenv",
    "With no API key the deterministic baseline takes over, and the policy engine still judges and prices it.");

  // -------------------------------------------------------------- 15. tests
  await deck(
    () => window.__demo.title("87 tests, 0 API calls",
      "Because the model only ever proposes, everything that decides is ordinary, testable code",
      ["<b>10</b> backend", "<b>67</b> AI platform", "<b>10</b> frontend", "<b>terraform validate</b> aws + gcp", "<b>helm lint</b> ×3"]),
    "The AI decision logic is covered deterministically in CI, on every pull request, for free.",
    5000,
  );

  await context.close();
  await browser.close();

  // Playwright names videos by an internal id; give it a predictable name.
  const produced = readdirSync(OUT).filter((f) => f.endsWith(".webm"));
  const newest = produced.map((f) => join(OUT, f)).sort()[produced.length - 1];
  const target = join(OUT, "idea-board-demo.webm");
  if (newest && newest !== target) renameSync(newest, target);
  console.log(`\nrecorded: ${target}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
