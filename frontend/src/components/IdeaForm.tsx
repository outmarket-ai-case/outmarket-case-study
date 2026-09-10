import { useState } from "react";

const MAX = 500;

interface Props {
  onSubmit: (content: string) => Promise<void>;
}

export function IdeaForm({ onSubmit }: Props) {
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);

  const trimmed = content.trim();
  const canSubmit = trimmed.length > 0 && trimmed.length <= MAX && !busy;

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
        placeholder="What should we build?"
        value={content}
        maxLength={MAX}
        rows={3}
        onChange={(e) => setContent(e.target.value)}
      />
      <div className="idea-form__footer">
        <span className="counter" aria-live="polite">
          {trimmed.length}/{MAX}
        </span>
        <button type="submit" disabled={!canSubmit}>
          {busy ? "Posting…" : "Post idea"}
        </button>
      </div>
    </form>
  );
}
