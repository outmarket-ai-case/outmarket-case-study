import { useCallback, useEffect, useState } from "react";
import { api, type Idea, type PlatformInfo } from "./api";
import { IdeaForm } from "./components/IdeaForm";
import { IdeaList } from "./components/IdeaList";

export default function App() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [platform, setPlatform] = useState<PlatformInfo | null>(null);
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
    // The badge tells you which cloud served this page -- handy when the same
    // release is live on two providers at once.
    api.platform().then(setPlatform).catch(() => setPlatform(null));
  }, [refresh]);

  const addIdea = useCallback(
    async (content: string) => {
      try {
        const created = await api.createIdea(content);
        setIdeas((prev) => [created, ...prev]);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not save that idea");
      }
    },
    [],
  );

  return (
    <main>
      <header>
        <h1>The Idea Board</h1>
        {platform && (
          <span className="badge" title={`release ${platform.version}`}>
            {platform.cloud} · {platform.environment}
          </span>
        )}
      </header>

      <IdeaForm onSubmit={addIdea} />

      {error && (
        <div className="error" role="alert">
          {error}
          <button type="button" onClick={() => void refresh()}>
            Retry
          </button>
        </div>
      )}

      {loading ? <p className="empty">Loading…</p> : <IdeaList ideas={ideas} />}
    </main>
  );
}
