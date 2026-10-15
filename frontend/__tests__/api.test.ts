/**
 * API client contract tests (mocked fetch).
 *
 * The client is the single boundary between UI and backend, so its error
 * mapping and request shapes are pinned here without touching the network.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE, ApiError, api } from "@/lib/api";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("error mapping", () => {
  it("maps HTTP error bodies to ApiError with status and detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "Alert X not found" }), {
            status: 404,
            headers: { "content-type": "application/json" },
          }),
      ),
    );

    const err = await api.investigation("nope").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).message).toBe("Alert X not found");
  });

  it("wraps network failures with the backend URL (status 0)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );

    const err = await api.health().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
    expect((err as ApiError).message).toContain(API_BASE);
  });
});

describe("request shapes", () => {
  it("POSTs investigations as JSON with alert_id + analyst", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ id: "inv:1" }), {
          status: 201,
          headers: { "content-type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const res = await api.runInvestigation("ALR-2026-10-0011", "tester");
    expect(res.id).toBe("inv:1");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`${API_BASE}/investigations`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      alert_id: "ALR-2026-10-0011",
      analyst: "tester",
    });
  });

  it("sends decisions to /actions/{id}/approve|reject", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ id: "act:1", status: "APPROVED" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.decide("act:1", "approve", "demo.analyst", "looks good");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    // Path segments are percent-encoded (":" -> "%3A"); FastAPI decodes
    // them back before the handler runs.
    expect(url).toBe(`${API_BASE}/actions/${encodeURIComponent("act:1")}/approve`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      analyst: "demo.analyst",
      reason: "looks good",
    });
  });

  it("builds neighborhood URLs with the hop bound", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ center_id: "x", hops: 2, nodes: [], edges: [] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.neighborhood("ALR-2026-10-0011", 3);
    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toBe(`${API_BASE}/graph/neighborhood/ALR-2026-10-0011?hops=3`);
  });
});
