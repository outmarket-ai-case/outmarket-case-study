/**
 * API client. All paths are relative: in every packaged image nginx proxies
 * /api and /healthz to the backend, so the same static bundle runs on any
 * cloud without a rebuild.
 */

export interface Idea {
  id: number;
  content: string;
  created_at: string;
}

export interface PlatformInfo {
  environment: string;
  cloud: string;
  version: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body: keep the status line */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  listIdeas: () => request<Idea[]>("/api/ideas"),
  createIdea: (content: string) =>
    request<Idea>("/api/ideas", { method: "POST", body: JSON.stringify({ content }) }),
  platform: () => request<PlatformInfo>("/healthz"),
};
