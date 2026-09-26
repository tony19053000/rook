// Make untrusted strings (event payloads, Bob output) safe to show. React already escapes HTML; this drops
// control characters so an ESC/OSC sequence or a stray NUL echoed from a repo never reaches the page. It is
// the web twin of src/rook/cli/tui/safe_text.py.

const WHITESPACE = /[\t\n\r\v\f]/g;
const CONTROLS = /[\x00-\x1f\x7f-\x9f]/g;

/** One display line: line breaks and tabs become spaces; other C0, DEL and C1 controls are dropped. */
export function clean(text: string): string {
  return String(text).replace(WHITESPACE, " ").replace(CONTROLS, "");
}

const NEWLINES = /\r\n?/g;
const INLINE_WHITESPACE = /[\t\v\f]/g;
const CONTROLS_BUT_NEWLINE = /[\x00-\x09\x0b-\x1f\x7f-\x9f]/g;

/** Like `clean`, but keeps line breaks: \r\n and lone \r become \n; tabs, \v and \f become spaces. */
export function cleanMultiline(text: string): string {
  return String(text).replace(NEWLINES, "\n").replace(INLINE_WHITESPACE, " ").replace(CONTROLS_BUT_NEWLINE, "");
}
