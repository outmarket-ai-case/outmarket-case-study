import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api";

function mockFetch(res: Partial<Response> & { json?: () => Promise<unknown> }) {
  const fn = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: "OK", json: async () => ({}), ...res });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("lists ideas from the relative path", async () => {
    const fetchMock = mockFetch({ json: async () => [{ id: 1, content: "hi", created_at: "2026-01-01T00:00:00Z" }] });
    const ideas = await api.listIdeas();
    expect(fetchMock).toHaveBeenCalledWith("/api/ideas", expect.objectContaining({ headers: { "Content-Type": "application/json" } }));
    expect(ideas).toHaveLength(1);
  });

  it("posts the content as JSON", async () => {
    const fetchMock = mockFetch({ json: async () => ({ id: 2, content: "new", created_at: "" }) });
    await api.createIdea("new");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", body: JSON.stringify({ content: "new" }) });
  });

  it("surfaces the server detail on failure", async () => {
    mockFetch({ ok: false, status: 422, statusText: "Unprocessable", json: async () => ({ detail: "content must not be blank" }) });
    await expect(api.createIdea(" ")).rejects.toThrow(ApiError);
    await expect(api.createIdea(" ")).rejects.toThrow("content must not be blank");
  });

  it("falls back to the status line for non-JSON errors", async () => {
    mockFetch({ ok: false, status: 502, statusText: "Bad Gateway", json: async () => { throw new Error("not json"); } });
    await expect(api.listIdeas()).rejects.toThrow("502 Bad Gateway");
  });
});
