import { describe, expect, it } from "vitest";
import { checkName, compact, cxTitle, diffLines, observedPairs, observedText, safeGithubUrl, short, stepText } from "./cardText";

describe("short and compact", () => {
  it("cleans control characters and cuts with an ellipsis", () => {
    expect(short("a\x1b[31mb\x00c\u009b", 10)).toBe("a[31mbc");
    expect(short("line1\nline2", 100)).toBe("line1 line2");
    expect(short("abcdef", 4)).toBe("abc…");
  });

  it("dumps non-strings as compact JSON", () => {
    expect(compact({ a: 1 })).toBe('{"a":1}');
    expect(compact("x")).toBe("x");
    expect(compact(undefined)).toBe("undefined");
  });
});

describe("steps and observed values (the TUI's step_text / observed_text)", () => {
  it("reads a step as actor: action(params)", () => {
    expect(stepText({ action: "refund", actor: "customer", params: { amount: 1 }, refs: { order_id: 0 } })).toBe("customer: refund(amount=1)");
    expect(stepText({ parallel: [{ action: "a" }, { action: "b" }] })).toBe("at the same time: a() | b()");
    expect(stepText({ action: "x\x1b]0;evil\x07", params: { "k\n": "v\x00" } })).toBe("x]0;evil(k =v)");
  });

  it("splits a flat observed dict into boxes, anything else is JSON", () => {
    expect(observedPairs({ paid: 1, refunded_total: 2 })).toEqual([["paid", "1"], ["refunded_total", "2"]]);
    expect(observedPairs({ nested: { a: 1 } })).toBeNull();
    expect(observedText({ paid: 1, refunded: 2 })).toBe("paid 1 · refunded 2");
    expect(observedText([1, 2])).toBe("[1,2]");
  });

  it("titles a counterexample", () => {
    expect(cxTitle("cx_001")).toBe("Counterexample #001");
    expect(cxTitle("weird")).toBe("Counterexample weird");
  });
});

describe("diffLines", () => {
  it("classifies red and green lines and cleans them", () => {
    const { lines, more } = diffLines("--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n ctx\n-old\x1b[0m\r\n+new\n");
    expect(lines.map((l) => l.kind)).toEqual(["meta", "meta", "hunk", "context", "remove", "add"]);
    expect(lines[4]!.text).toBe("-old[0m");
    expect(more).toBe(0);
  });

  it("keeps the first lines of a long diff", () => {
    const { lines, more } = diffLines(Array.from({ length: 10 }, (_, i) => `+${i}`).join("\n"), 4);
    expect(lines).toHaveLength(4);
    expect(more).toBe(6);
    expect(diffLines("").lines).toEqual([]);
  });

  it("names the verify checks", () => {
    expect(checkName("fresh_search")).toBe("Fresh search");
    expect(checkName("new_check")).toBe("New check");
  });
});

describe("safeGithubUrl", () => {
  it("allows only https://github.com/ URLs", () => {
    expect(safeGithubUrl("https://github.com/acme/shop/pull/88")).toBe("https://github.com/acme/shop/pull/88");
    for (const bad of [
      "javascript:alert(1)",
      "http://github.com/acme/shop/pull/1",
      "https://github.com.evil.test/x",
      "https://evil.test/https://github.com/",
      "https://user:pw@github.com/acme",
      "https://github.com:8443/acme",
      "https://github.com/acme\n/x",
      " JAVASCRIPT:alert(1)//https://github.com/",
      "data:text/html,<script>alert(1)</script>",
      42,
      null,
    ]) {
      expect(safeGithubUrl(bad)).toBeNull();
    }
  });
});
