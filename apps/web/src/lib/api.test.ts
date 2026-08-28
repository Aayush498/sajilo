/**
 * Tests for the API client's session handling.
 *
 * This is the riskiest code in the frontend. The API rotates refresh tokens
 * and revokes the entire session if one is reused, so getting the retry logic
 * wrong does not merely fail to refresh — it signs the user out.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthSession } from "./api";

const BASE = "http://localhost:8000/api/v1";

/** Minimal localStorage so the module under test can run outside a browser. */
function installLocalStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  });
  vi.stubGlobal("window", {});
  vi.stubGlobal("navigator", { onLine: true });
  return store;
}

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
    json: async () => body,
  } as Response;
}

const session = (n: number): AuthSession => ({
  access_token: `access-${n}`,
  refresh_token: `refresh-${n}`,
  expires_in: 900,
  user: {
    id: "u1",
    phone: "+9779841000100",
    full_name: "Test",
    email: null,
    role: "customer",
    locale: "en",
  },
  is_new_user: false,
});

describe("api client session handling", () => {
  let store: Map<string, string>;

  beforeEach(async () => {
    vi.resetModules();
    store = installLocalStorage();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("refreshes once and retries the original request", async () => {
    const { api, tokens } = await import("./api");
    tokens.save(session(1));

    const fetchMock = vi.fn(async (url: string) => {
      if (url === `${BASE}/auth/refresh`) return jsonResponse(200, session(2));
      // The first attempt carries the stale token and is rejected; the retry
      // carries the refreshed one and succeeds.
      return store.get("sajilo.access") === "access-2"
        ? jsonResponse(200, { id: "u1" })
        : jsonResponse(401, { error: { code: "TOKEN_EXPIRED" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.get("/users/me")).resolves.toEqual({ id: "u1" });

    const refreshCalls = fetchMock.mock.calls.filter((c) => c[0] === `${BASE}/auth/refresh`);
    expect(refreshCalls).toHaveLength(1);
    expect(tokens.access).toBe("access-2");
  });

  it("sends only ONE refresh when several requests expire together", async () => {
    // This is the whole point. /worker fires four requests at once. Four
    // separate refreshes would mean three arriving with an already-rotated
    // token, which the API treats as theft and answers by killing the
    // session — the exact opposite of staying signed in.
    const { api, tokens } = await import("./api");
    tokens.save(session(1));

    let refreshes = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === `${BASE}/auth/refresh`) {
          refreshes += 1;
          // A real refresh is not instant; the race only shows up if it isn't.
          await new Promise((r) => setTimeout(r, 10));
          return jsonResponse(200, session(2));
        }
        return store.get("sajilo.access") === "access-2"
          ? jsonResponse(200, { ok: true })
          : jsonResponse(401, { error: { code: "TOKEN_EXPIRED" } });
      }),
    );

    const results = await Promise.all([
      api.get("/worker/profile"),
      api.get("/worker/jobs"),
      api.get("/worker/available-jobs"),
      api.get("/worker/earnings"),
    ]);

    expect(results).toHaveLength(4);
    expect(refreshes).toBe(1);
  });

  it("clears the session and notifies once the refresh itself fails", async () => {
    const { api, tokens, setSessionLostHandler } = await import("./api");
    tokens.save(session(1));

    const lost = vi.fn();
    setSessionLostHandler(lost);

    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url === `${BASE}/auth/refresh`
          ? jsonResponse(401, { error: { code: "REFRESH_REUSED" } })
          : jsonResponse(401, { error: { code: "SESSION_REVOKED" } }),
      ),
    );

    await expect(api.get("/users/me")).rejects.toThrow();
    expect(tokens.access).toBeNull();
    expect(tokens.refresh).toBeNull();
    expect(lost).toHaveBeenCalledOnce();
  });

  it("does not try to refresh an unauthenticated call", async () => {
    const { api } = await import("./api");
    // No tokens saved at all — browsing the catalogue signed out.
    const fetchMock = vi.fn(async (_url: string) =>
      jsonResponse(401, { error: { code: "NOPE" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.get("/catalog/services", false)).rejects.toThrow();
    expect(fetchMock.mock.calls.some((c) => c[0] === `${BASE}/auth/refresh`)).toBe(false);
  });

  it("turns a dead network into a readable error, not a raw TypeError", async () => {
    const { api } = await import("./api");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    await expect(api.get("/catalog/services", false)).rejects.toMatchObject({
      code: "NETWORK",
      status: 0,
    });
  });

  it("says so plainly when the device is offline", async () => {
    const { api } = await import("./api");
    vi.stubGlobal("navigator", { onLine: false });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    await expect(api.get("/catalog/services", false)).rejects.toThrow(/offline/i);
  });
});
