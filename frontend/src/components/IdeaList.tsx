import type { Idea } from "../api";

function relative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString();
}

export function IdeaList({ ideas }: { ideas: Idea[] }) {
  if (ideas.length === 0) {
    return <p className="empty">No ideas yet. Be the first.</p>;
  }
  return (
    <ul className="idea-list">
      {ideas.map((idea) => (
        <li key={idea.id}>
          <p>{idea.content}</p>
          <time dateTime={idea.created_at}>{relative(idea.created_at)}</time>
        </li>
      ))}
    </ul>
  );
}
