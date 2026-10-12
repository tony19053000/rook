import { describe, expect, it } from "vitest";
import type { RepoOption } from "./api";
import { bobModeLabel, filterGroups, firstName, pickerGroups } from "./pages";
import { GUEST, type Session } from "./session";

const DEMO: RepoOption = { kind: "demo", ref: "tony19053000/shop-app", name: "shop-app", private: false, language: "Node.js" };
const GH: RepoOption = { kind: "github", ref: "aayush/billing", name: "aayush/billing", private: true, language: "Python" };
const USER: Session = { kind: "user", name: "Aayush Kumar", email: "a@example.com", githubConnected: true };

describe("home helpers (04 §3.2, §3.3)", () => {
  it("firstName: the first word of the name, else the email's local part, cleaned", () => {
    expect(firstName(USER)).toBe("Aayush");
    expect(firstName({ ...USER, name: "" })).toBe("a");
    expect(firstName({ ...USER, name: "  Ada\tLovelace " })).toBe("Ada");
    expect(firstName({ ...USER, name: "Eve\x1b[2J" })).not.toContain("\x1b");
    expect(firstName(GUEST)).toBe("");
  });

  it("bobModeLabel: an example follows the server's Bob mode, your own repo is live, and unknown claims neither", () => {
    expect(bobModeLabel(DEMO, "replay")).toBe("IBM Bob · recorded answers");
    expect(bobModeLabel(DEMO, "live")).toBe("IBM Bob · live");
    expect(bobModeLabel(DEMO)).toBe("IBM Bob");
    expect(bobModeLabel(GH)).toBe("IBM Bob · live");
    expect(bobModeLabel(GH, "replay")).toBe("IBM Bob · live");
    expect(bobModeLabel(null, "replay")).toBe("IBM Bob");
  });

  it("filterGroups: matches name or owner/name, case-insensitive, keeps the GitHub group shape", () => {
    const groups = pickerGroups([GH, DEMO], USER);
    expect(filterGroups(groups, "")).toBe(groups);
    expect(filterGroups(groups, "BILL")).toEqual({ github: [GH], demo: [], connectGithub: false });
    expect(filterGroups(groups, "tony19053000")).toEqual({ github: [], demo: [DEMO], connectGithub: false });
    expect(filterGroups(pickerGroups([DEMO], GUEST), "zzz")).toEqual({ github: null, demo: [], connectGithub: false });
  });
});
