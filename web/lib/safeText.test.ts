import { describe, expect, it } from "vitest";
import { clean, cleanMultiline } from "./safeText";

describe("safeText", () => {
  it("clean drops C0/C1 controls and flattens line breaks", () => {
    expect(clean("a\x1b]0;pwned\x07b")).toBe("a]0;pwnedb");
    expect(clean("one\ntwo\tthree\r")).toBe("one two three ");
    expect(clean("x\x00\x7f\x9by")).toBe("xy");
    expect(clean("₹100 · ✓")).toBe("₹100 · ✓");
  });

  it("cleanMultiline keeps newlines", () => {
    expect(cleanMultiline("a\r\nb\rc\x1b[0m\td")).toBe("a\nb\nc[0m d");
  });
});
