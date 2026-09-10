import type { Idea } from "../api";
import { IconBulb, IconClock } from "./Icons";

function relative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function IdeaList({ ideas }: { ideas: Idea[] }) {
  if (ideas.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-state__icon">
          <IconBulb size={26} />
        </span>
        <h3>No ideas yet</h3>
        <p>Be the first to post one.</p>
      </div>
    );
  }

  return (
    <ul className="idea-list">
      {ideas.map((idea) => (
        <li key={idea.id} data-tone={idea.id % 5}>
          <span className="idea-list__badge" data-tone={idea.id % 5}>
            #{idea.id}
          </span>
          <div className="idea-list__content">
            <p>{idea.content}</p>
            <time dateTime={idea.created_at}>
              <IconClock /> {relative(idea.created_at)}
            </time>
          </div>
        </li>
      ))}
    </ul>
  );
}
