import { useEffect, useMemo, useRef, useState } from "react";
import { marked } from "marked";
import { DOC_PAGES, extractToc, fetchDoc, type TocEntry } from "../docs";
import { IconBulb, IconCloud, IconLink, IconSparkles } from "./Icons";

marked.setOptions({ gfm: true, breaks: false });

const ICONS = {
  bulb: IconBulb,
  cloud: IconCloud,
  sparkles: IconSparkles,
} as const;

/**
 * Renders the project documentation inside the app.
 *
 * The markdown is first-party content baked into the image at build time, not
 * user input, and the page's CSP forbids inline and third-party script
 * execution -- so rendering it via innerHTML cannot introduce a script that
 * would actually run. If these documents ever became user-editable this would
 * need a sanitiser.
 */
export function DocsView({ slug }: { slug: string }) {
  const page = useMemo(
    () => DOC_PAGES.find((p) => p.slug === slug) ?? DOC_PAGES[0],
    [slug],
  );

  const [html, setHtml] = useState<string | null>(null);
  const [toc, setToc] = useState<TocEntry[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setHtml(null);
    setToc([]);
    setActiveId("");
    setError(null);
    window.scrollTo({ top: 0 });

    fetchDoc(page)
      .then((markdown) => {
        if (cancelled) return;
        // Parse once, add heading ids, then hand the same document to React.
        const doc = new DOMParser().parseFromString(
          marked.parse(markdown) as string,
          "text/html",
        );
        setToc(extractToc(doc.body));
        setHtml(doc.body.innerHTML);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load the document");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [page]);

  // Highlight the section currently in view. Purely decorative, so it degrades
  // silently where IntersectionObserver is unavailable.
  useEffect(() => {
    const root = bodyRef.current;
    if (!root || toc.length === 0 || typeof IntersectionObserver === "undefined") return;

    const headings = toc
      .map((entry) => root.querySelector<HTMLElement>(`#${CSS.escape(entry.id)}`))
      .filter((el): el is HTMLElement => el !== null);

    const observer = new IntersectionObserver(
      (records) => {
        const visible = records
          .filter((r) => r.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]?.target.id) setActiveId(visible[0].target.id);
      },
      // Bias the band towards the top of the viewport so the highlighted entry
      // matches what the reader is actually looking at.
      { rootMargin: "-88px 0px -70% 0px", threshold: 0 },
    );

    headings.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [toc, html]);

  const Icon = ICONS[page.icon];

  return (
    <div className="docs" data-doc={page.tone}>
      <aside className="docs__side">
        <nav aria-label="Documents" className="docs__docnav">
          {DOC_PAGES.map((p) => {
            const PageIcon = ICONS[p.icon];
            const active = p.slug === page.slug;
            return (
              <a
                key={p.slug}
                href={`#/docs/${p.slug}`}
                className={active ? "doccard doccard--active" : "doccard"}
                data-tone={p.tone}
                aria-current={active ? "page" : undefined}
              >
                <span className="doccard__icon">
                  <PageIcon size={17} />
                </span>
                <span className="doccard__text">
                  <strong>{p.title}</strong>
                  <span>{p.blurb}</span>
                </span>
              </a>
            );
          })}
        </nav>

        {toc.length > 0 && (
          <nav aria-label="On this page" className="toc">
            <p className="toc__title">On this page</p>
            <ul>
              {toc.map((entry) => (
                <li key={entry.id} className={`toc__item toc__item--h${entry.level}`}>
                  <a
                    href={`#${entry.id}`}
                    className={entry.id === activeId ? "toc__link toc__link--active" : "toc__link"}
                    onClick={(e) => {
                      // Plain anchors would rewrite the hash route and unmount
                      // the view, so scrolling is handled directly.
                      e.preventDefault();
                      bodyRef.current
                        ?.querySelector(`#${CSS.escape(entry.id)}`)
                        ?.scrollIntoView({ behavior: "smooth", block: "start" });
                      setActiveId(entry.id);
                    }}
                  >
                    {entry.text}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </aside>

      <article className="docs__body">
        <div className="docs__head">
          <span className="docs__head-icon">
            <Icon size={20} />
          </span>
          <div>
            <h2>{page.title}</h2>
            <p>{page.blurb}</p>
          </div>
          <a
            className="docs__source"
            href={`/docs/${page.path.split("/").pop()}`}
            target="_blank"
            rel="noreferrer"
            title="View the raw markdown"
          >
            <IconLink size={14} />
            raw
          </a>
        </div>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {!error && html === null && <p className="empty">Loading {page.title}…</p>}
        {html !== null && (
          <div className="markdown" ref={bodyRef} dangerouslySetInnerHTML={{ __html: html }} />
        )}
      </article>
    </div>
  );
}
