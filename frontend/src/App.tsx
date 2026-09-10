import { useCallback, useEffect, useState } from "react";
import { api, type Idea, type PlatformInfo } from "./api";
import { IdeaForm } from "./components/IdeaForm";
import { IdeaList } from "./components/IdeaList";
import { DocsView } from "./components/DocsView";
import { DOC_PAGES } from "./docs";
import {
  IconAlert,
  IconBoard,
  IconCloud,
  IconDocs,
  IconGithub,
  IconRefresh,
  IconSparkles,
  Logo,
} from "./components/Icons";

const REPO_URL = "https://github.com/outmarket-ai-case/outmarket-case-study";

/**
 * Hash routing rather than the History API: the app is served by nginx with a
 * `try_files … /index.html` fallback, and hash routes never reach the server at
 * all, so deep links keep working with no extra nginx rules on any provider.
 */
type Route = { view: "board" } | { view: "docs"; slug: string };

function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "docs") {
    return { view: "docs", slug: parts[1] ?? DOC_PAGES[0].slug };
  }
  return { view: "board" };
}

function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

function Board() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setIdeas(await api.listIdeas());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reach the API");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const addIdea = useCallback(async (content: string) => {
    try {
      const created = await api.createIdea(content);
      setIdeas((prev) => [created, ...prev]);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save that idea");
    }
  }, []);

  return (
    <div className="board">
      <div className="board__intro">
        <span className="eyebrow">
          <IconSparkles size={13} /> live demo
        </span>
        <h2>What should we build?</h2>
        <p>
          Post an idea. It goes to a FastAPI service and into PostgreSQL — the same code path
          that runs on EKS and GKE.
        </p>
      </div>

      <IdeaForm onSubmit={addIdea} />

      {error && (
        <div className="error" role="alert">
          <IconAlert size={17} />
          <span>{error}</span>
          <button type="button" onClick={() => void refresh()}>
            <IconRefresh /> Retry
          </button>
        </div>
      )}

      {!loading && ideas.length > 0 && (
        <p className="board__count">
          {ideas.length} {ideas.length === 1 ? "idea" : "ideas"} · newest first
        </p>
      )}

      {loading ? <p className="empty">Loading…</p> : <IdeaList ideas={ideas} />}
    </div>
  );
}

export default function App() {
  const route = useRoute();
  const [platform, setPlatform] = useState<PlatformInfo | null>(null);

  useEffect(() => {
    // The badge tells you which cloud served this page -- handy when the same
    // release is live on two providers at once.
    api.platform().then(setPlatform).catch(() => setPlatform(null));
  }, []);

  return (
    <>
      <header className="topbar">
        <div className="topbar__inner">
          <a className="brand" href="#/">
            <Logo />
            <span className="brand__text">
              <strong>Idea Board</strong>
              <span>AI-first, cloud-agnostic platform</span>
            </span>
          </a>

          <nav className="tabs" aria-label="Sections">
            <a href="#/" className={route.view === "board" ? "tab tab--active" : "tab"}>
              <IconBoard size={16} /> Board
            </a>
            <a href="#/docs" className={route.view === "docs" ? "tab tab--active" : "tab"}>
              <IconDocs size={16} /> Docs
            </a>
          </nav>

          <div className="topbar__meta">
            {platform && (
              <span className="badge" data-cloud={platform.cloud} title={`release ${platform.version}`}>
                <IconCloud size={14} />
                {platform.cloud} · {platform.environment}
              </span>
            )}
            <a className="iconbtn" href={REPO_URL} target="_blank" rel="noreferrer" title="Source on GitHub">
              <IconGithub />
            </a>
          </div>
        </div>
      </header>

      <main className={route.view === "docs" ? "main main--wide" : "main"}>
        {route.view === "board" ? <Board /> : <DocsView slug={route.slug} />}
      </main>

      <footer className="footer">
        <span>
          Served by <code>{platform?.cloud ?? "…"}</code> · release{" "}
          <code>{platform?.version ?? "…"}</code>
        </span>
        <a href={REPO_URL} target="_blank" rel="noreferrer">
          View the source
        </a>
      </footer>
    </>
  );
}
