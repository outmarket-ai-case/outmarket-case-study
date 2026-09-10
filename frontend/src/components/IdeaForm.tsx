import { useState } from "react";
import { IconSend } from "./Icons";

const MAX = 500;

interface Props {
  onSubmit: (content: string) => Promise<void>;
}

export function IdeaForm({ onSubmit }: Props) {
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);

  const trimmed = content.trim();
  const canSubmit = trimmed.length > 0 && trimmed.length <= MAX && !busy;
  const pct = Math.min(100, (trimmed.length / MAX) * 100);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    try {
      await onSubmit(trimmed);
      setContent("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="idea-form" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor="idea-input">
        Your idea
      </label>
      <textarea
        id="idea-input"
        placeholder="A short, concrete idea…"
        value={content}
        maxLength={MAX}
        rows={3}
        onChange={(e) => setContent(e.target.value)}
      />
      <div className="idea-form__footer">
        <div className="meter" aria-hidden>
          <div className="meter__fill" style={{ width: `${pct}%` }} />
        </div>
        <span className="counter" aria-live="polite">
          {trimmed.length}/{MAX}
        </span>
        <button type="submit" disabled={!canSubmit}>
          <IconSend />
          {busy ? "Posting…" : "Post idea"}
        </button>
      </div>
    </form>
  );
}
