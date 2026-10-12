import { describe, expect, it } from "vitest";
import { clean, cleanMultiline, plainMarkdown } from "./safeText";

const ESC = "\x1b";

describe("safeText", () => {
  it("clean drops C0/C1 controls and flattens line breaks", () => {
    expect(clean("one\ntwo\tthree\r")).toBe("one two three ");
    expect(clean("x\x00\x7fy")).toBe("xy");
    expect(clean("₹100 · ✓")).toBe("₹100 · ✓");
  });

  it("strips whole ANSI sequences, not just the ESC byte (ROOK-052: the verify card showed `[2m   Duration [22m 2.77s`)", () => {
    const raw = `${ESC}[2m   Duration ${ESC}[22m 2.77s`;
    expect(clean(raw)).toBe("   Duration  2.77s");
    expect(clean(raw)).not.toContain("[2m   Duration [22m 2.77s");
    expect(clean(raw)).not.toMatch(/\[\d+m/);
    expect(cleanMultiline(`${ESC}[1m${ESC}[32m ✓ ${ESC}[39m${ESC}[22mtests/refund.test.js\n${raw}`)).toBe(" ✓ tests/refund.test.js\n   Duration  2.77s");
  });

  it("strips CSI with parameters, the C1 CSI byte, OSC titles and links, and other escapes", () => {
    expect(clean(`a${ESC}[38;5;196mred${ESC}[0m`)).toBe("ared");
    expect(clean(`a${ESC}[2J${ESC}[?25lb`)).toBe("ab");
    expect(clean("a\x9b31mb")).toBe("ab");
    expect(clean(`a${ESC}]0;pwned\x07b`)).toBe("ab");
    expect(clean(`${ESC}]8;;https://evil.example${ESC}\\link${ESC}]8;;${ESC}\\`)).toBe("link");
    expect(clean(`a${ESC}(Bb${ESC}=c`)).toBe("abc");
  });

  it("an unterminated sequence loses only its introducer, never the rest of the line", () => {
    expect(clean(`a${ESC}]0;no end`)).toBe("a0;no end");
    expect(clean(`total ${ESC}`)).toBe("total ");
    expect(clean("price [2m] and array[0m]")).toBe("price [2m] and array[0m]"); // no ESC: ordinary text is kept
  });

  it("cleanMultiline keeps newlines", () => {
    expect(cleanMultiline(`a\r\nb\rc${ESC}[0m\td`)).toBe("a\nb\nc d");
  });
});

describe("plainMarkdown (ROOK-052: agent rows showed Bob's raw Markdown)", () => {
  it("reads a file link as its target: [`app.py`](app.py:214) is app.py:214", () => {
    expect(plainMarkdown("[`app.py`](app.py:214)")).toBe("app.py:214");
    expect(plainMarkdown("The check in [`app.py`](app.py:214) ignores earlier refunds")).toBe("The check in app.py:214 ignores earlier refunds");
    expect(plainMarkdown("[refund handler](src/refunds.js:42)")).toBe("refund handler (src/refunds.js:42)");
    expect(plainMarkdown("[](app.py:3)")).toBe("app.py:3");
  });

  it("drops backticks and bold marks, and leaves ordinary text alone", () => {
    expect(plainMarkdown("`refund_total <= paid` in `app.py`")).toBe("refund_total <= paid in app.py");
    expect(plainMarkdown("**Root cause**: no cap")).toBe("Root cause: no cap");
    expect(plainMarkdown("a ** b ** c, items[0] (x)")).toBe("a ** b ** c, items[0] (x)");
  });

  it("returns text only: a hostile link or tag stays inert characters", () => {
    expect(plainMarkdown("[click](javascript:alert(1))")).toBe("[click](javascript:alert(1))");
    expect(plainMarkdown("[x](javascript:alert)")).toBe("x (javascript:alert)");
    expect(plainMarkdown("[<img src=x>](a.py:1)")).toBe("<img src=x> (a.py:1)");
  });
});
