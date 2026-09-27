import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { finishGithubConnect, isInstallUrl, isSetupReturn, setupParams, startGithubConnect } from "./github";

const STATE = "Abc_def-123".repeat(4);
const INSTALL = `https://github.com/apps/rook-invariants/installations/new?state=${STATE}`;

describe("the install URL (no open redirect)", () => {
  it("accepts only GitHub's App install page with a state", () => {
    expect(isInstallUrl(INSTALL)).toBe(true);
    for (const bad of [
      `https://evil.example/apps/rook-invariants/installations/new?state=${STATE}`,
      `http://github.com/apps/rook-invariants/installations/new?state=${STATE}`,
      `https://github.com.evil.example/apps/rook-invariants/installations/new?state=${STATE}`,
      `https://user:pw@github.com/apps/rook-invariants/installations/new?state=${STATE}`,
      `https://github.com:8443/apps/rook-invariants/installations/new?state=${STATE}`,
      `https://github.com/login?return_to=https://evil.example&state=${STATE}`,
      "https://github.com/apps/rook-invariants/installations/new",
      "javascript:alert(1)",
      42,
    ]) {
      expect(isInstallUrl(bad)).toBe(false);
    }
  });

  it("startGithubConnect goes there, or explains why not", async () => {
    const went: string[] = [];
    expect(await startGithubConnect({ githubInstallUrl: async () => ({ url: INSTALL }) }, (u) => went.push(u))).toBeNull();
    expect(went).toEqual([INSTALL]);
    expect(await startGithubConnect({ githubInstallUrl: async () => ({ url: "https://evil.example/" }) }, (u) => went.push(u))).toMatch(/unexpected/);
    const fail = (status: number) => ({
      githubInstallUrl: async (): Promise<{ url: string }> => {
        throw new ApiError(status, "x");
      },
    });
    expect(await startGithubConnect(fail(401), (u) => went.push(u))).toMatch(/Sign in first/);
    expect(await startGithubConnect(fail(501), (u) => went.push(u))).toMatch(/not set up/);
    expect(went).toHaveLength(1);
  });
});

describe("the setup return", () => {
  it("reads GitHub's query and drops anything malformed", () => {
    expect(setupParams(`?installation_id=4242&setup_action=install&state=${STATE}`)).toEqual({
      installation_id: "4242",
      state: STATE,
      setup_action: "install",
    });
    expect(setupParams(`?installation_id=1&state=${STATE}&code=abc123&setup_action=<b>`)).toEqual({ installation_id: "1", state: STATE, code: "abc123" });
    expect(setupParams(`?installation_id=abc&state=${STATE}`)).toBeNull();
    expect(setupParams("?installation_id=5&state=short")).toBeNull();
    expect(setupParams("?installation_id=5")).toBeNull();
    expect(isSetupReturn("?installation_id=5&state=x")).toBe(true);
    expect(isSetupReturn("?code=x")).toBe(false);
  });

  it("sends the callback once per state and maps failures to a next step", async () => {
    let calls = 0;
    const ok = {
      githubCallback: async () => {
        calls += 1;
        return { ok: true };
      },
    };
    const params = { installation_id: "7", state: `${STATE}-once` };
    expect(await Promise.all([finishGithubConnect(ok, params), finishGithubConnect(ok, params)])).toEqual([null, null]);
    expect(calls).toBe(1);
    const failing = (status: number) => ({
      githubCallback: async (): Promise<{ ok: boolean }> => {
        throw new ApiError(status, "x");
      },
    });
    expect(await finishGithubConnect(failing(403), { installation_id: "7", state: `${STATE}-403` })).toMatch(/could not verify/);
    expect(await finishGithubConnect(failing(401), { installation_id: "7", state: `${STATE}-401` })).toMatch(/Sign in to Rook first/);
    expect(await finishGithubConnect(failing(429), { installation_id: "7", state: `${STATE}-429` })).toMatch(/Too many/);
  });
});
