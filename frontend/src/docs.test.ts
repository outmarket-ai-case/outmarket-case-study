import { describe, expect, it } from "vitest";
import { DOC_PAGES, extractToc, slugify } from "./docs";

describe("slugify", () => {
  it("produces GitHub-style anchors so in-document links keep working", () => {
    expect(slugify("The claim, stated precisely")).toBe("the-claim-stated-precisely");
    expect(slugify("Why not one Terraform root with a `cloud` variable?")).toBe(
      "why-not-one-terraform-root-with-a-cloud-variable",
    );
  });

  it("survives punctuation-only and empty headings", () => {
    expect(slugify("---")).toBe("");
    expect(slugify("   ")).toBe("");
  });
});

describe("extractToc", () => {
  function body(html: string): HTMLElement {
    return new DOMParser().parseFromString(html, "text/html").body;
  }

  it("collects h2 and h3, assigns ids, and ignores deeper levels", () => {
    const root = body("<h1>Title</h1><h2>First</h2><h3>Nested</h3><h4>Ignored</h4><h2>Second</h2>");
    const toc = extractToc(root);

    expect(toc.map((t) => [t.text, t.level])).toEqual([
      ["First", 2],
      ["Nested", 3],
      ["Second", 2],
    ]);
    expect(root.querySelector("h2")!.id).toBe("first");
    expect(root.querySelector("h4")!.id).toBe("");
  });

  it("de-duplicates repeated headings, which the real docs contain", () => {
    const toc = extractToc(body("<h2>Verification</h2><h2>Verification</h2>"));
    expect(toc.map((t) => t.id)).toEqual(["verification", "verification-1"]);
  });

  it("skips empty headings rather than emitting a blank entry", () => {
    expect(extractToc(body("<h2></h2><h2>Real</h2>"))).toHaveLength(1);
  });
});

describe("DOC_PAGES", () => {
  it("has unique slugs and an icon for each page", () => {
    const slugs = DOC_PAGES.map((p) => p.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
    expect(DOC_PAGES.every((p) => p.icon && p.path.endsWith(".md"))).toBe(true);
  });
});
