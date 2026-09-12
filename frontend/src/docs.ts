/**
 * Documentation loading and structure.
 *
 * The markdown files are copied into the nginx document root at image build
 * time and fetched over the same origin, so the docs ship *with* the running
 * system rather than living only in the repository. No external requests, which
 * matters because the page runs under a `default-src 'self'` CSP.
 */

export interface DocPage {
  slug: string;
  title: string;
  blurb: string;
  path: string;
  icon: "bulb" | "cloud" | "sparkles" | "cost" | "reliability" | "scale" | "security" | "flow";
  /** Drives the accent hue for this document, via a `data-doc` attribute in CSS. */
  tone: "violet" | "teal" | "amber" | "green" | "sky" | "rose" | "slate" | "indigo";
}

export const DOC_PAGES: DocPage[] = [
  {
    slug: "readme",
    title: "Overview",
    blurb: "Architecture, how to run it, and what was verified",
    path: "/docs/README.md",
    icon: "bulb",
    tone: "violet",
  },
  {
    slug: "deployment-flow",
    title: "Deployment flow",
    blurb: "Compose, minikube and cloud, end to end",
    path: "/docs/deployment-flow.md",
    icon: "flow",
    tone: "indigo",
  },
  {
    slug: "cloud-agnostic",
    title: "Cloud-agnostic design",
    blurb: "One contract, two clouds, a two-line diff",
    path: "/docs/cloud-agnostic.md",
    icon: "cloud",
    tone: "teal",
  },
  {
    slug: "ai-integration",
    title: "AI integration",
    blurb: "The model proposes, a policy engine decides",
    path: "/docs/ai-integration.md",
    icon: "sparkles",
    tone: "amber",
  },
  {
    slug: "cost",
    title: "Cost",
    blurb: "$622/month, generated from the policy engine's own model",
    path: "/docs/cost.md",
    icon: "cost",
    tone: "green",
  },
  {
    slug: "reliability",
    title: "Reliability",
    blurb: "Failure scenarios, and what actually broke",
    path: "/docs/reliability.md",
    icon: "reliability",
    tone: "rose",
  },
  {
    slug: "scalability",
    title: "Scalability",
    blurb: "Capacity maths, and the connection ceiling",
    path: "/docs/scalability.md",
    icon: "scale",
    tone: "sky",
  },
  {
    slug: "security",
    title: "Security",
    blurb: "No credential in the repo; the AI attack surface",
    path: "/docs/security.md",
    icon: "security",
    tone: "slate",
  },
];

export async function fetchDoc(page: DocPage): Promise<string> {
  const res = await fetch(page.path);
  if (!res.ok) {
    throw new Error(`Could not load ${page.title} (${res.status})`);
  }
  return res.text();
}

/* ------------------------------------------------------------------ */
/* Table of contents                                                   */
/* ------------------------------------------------------------------ */

export interface TocEntry {
  id: string;
  text: string;
  level: 2 | 3;
}

/** GitHub-style heading slug, so in-document links keep working. */
export function slugify(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[`*_~]/g, "")
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

/**
 * Give every h2/h3 a stable id and return the resulting outline.
 *
 * Done on the parsed document rather than with a regex over the HTML string:
 * these documents contain fenced code blocks with `#` comments and angle
 * brackets, and a regex would happily mangle them.
 */
export function extractToc(root: ParentNode): TocEntry[] {
  const entries: TocEntry[] = [];
  const seen = new Map<string, number>();

  root.querySelectorAll("h2, h3").forEach((el) => {
    const text = el.textContent?.trim() ?? "";
    if (!text) return;

    // Duplicate headings are common ("Verification" in two docs), so ids are
    // de-duplicated the way GitHub does it.
    const base = slugify(text) || "section";
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    const id = count === 0 ? base : `${base}-${count}`;

    el.id = id;
    entries.push({ id, text, level: el.tagName === "H2" ? 2 : 3 });
  });

  return entries;
}
