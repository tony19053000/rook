import { describe, expect, it } from "vitest";
import { ApiError, TIMEOUT_STATUS } from "./api";
import { runDelete, STILL_DELETING } from "./pages";

// ROOK-052: how a deletion's result reads (lib/pages.runDelete), for DELETE /runs/{id} and DELETE /me/data.

const fail = (error: unknown) => () => Promise.reject(error);

describe("runDelete", () => {
  it("a confirmed deletion is deleted", async () => {
    expect(await runDelete(async () => ({ ok: true }), "run")).toEqual({ kind: "deleted" });
  });

  it.each([TIMEOUT_STATUS, 504, 524])("no answer in time (HTTP %i) is pending: still deleting, refresh in a moment", async (status) => {
    expect(await runDelete(fail(new ApiError(status, "")), "run")).toEqual({ kind: "pending", message: STILL_DELETING });
    expect(await runDelete(fail(new ApiError(status, "")), "data")).toEqual({ kind: "pending", message: STILL_DELETING });
  });

  it("a network failure and a server error can be retried", async () => {
    expect(await runDelete(fail(new TypeError("offline")), "run")).toMatchObject({ kind: "error", retryable: true });
    expect(await runDelete(fail(new ApiError(500, "boom")), "data")).toEqual({
      kind: "error",
      message: "The server had a problem (HTTP 500). Try again.",
      retryable: true,
    });
    expect(await runDelete(fail(new ApiError(429, "slow down", 120)), "run")).toMatchObject({
      message: "Too many requests right now. Try again in about 2 minutes.",
      retryable: true,
    });
  });

  it("404 on a run (gone, or not yours) and 401 are final; 403 shows the server's reason", async () => {
    expect(await runDelete(fail(new ApiError(404, "Run not found")), "run")).toEqual({
      kind: "error",
      message: "This run is already gone, or it belongs to someone else.",
      retryable: false,
    });
    expect(await runDelete(fail(new ApiError(401, "")), "data")).toMatchObject({ kind: "error", retryable: false });
    expect(await runDelete(fail(new ApiError(403, "Cross-site request refused")), "data")).toMatchObject({ message: "Cross-site request refused" });
    expect(await runDelete(fail(new ApiError(403, "")), "data")).toMatchObject({ message: "The server refused this request. Reload the page and try again." });
  });

  it("an older server without the route (404 on /me/data) points to email instead of a retry", async () => {
    const outcome = await runDelete(fail(new ApiError(404, "Not Found")), "data");
    expect(outcome).toMatchObject({ kind: "error", retryable: false });
    expect(outcome.kind === "error" && outcome.message).toContain("Email us");
  });
});
