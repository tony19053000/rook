// Make untrusted strings (event payloads, Bob output) safe to show. React already escapes HTML; this drops
// terminal escape sequences and control characters so an ESC/OSC sequence or a stray NUL echoed from a repo
// never reaches the page. It is the web twin of src/rook/cli/tui/safe_text.py.

// Whole ANSI sequences, removed before the lone controls (dropping only the ESC byte would leave "[2m" behind):
// CSI (ESC [ … final, or the C1 byte 0x9b), then OSC and DCS/SOS/PM/APC strings up to their terminator (BEL or
// ST), then any other two-byte ESC sequence. An unterminated string loses only its introducer.
const ANSI =
  // eslint-disable-next-line no-control-regex -- matching control characters is the point here
  /(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]|(?:\x1b\]|\x9d)[^\x07\x1b\x9c]*(?:\x07|\x1b\\|\x9c)|\x1b[PX^_][^\x1b\x9c]*(?:\x1b\\|\x9c)|\x1b[ -/]*[0-~]/g;
const WHITESPACE = /[\t\n\r\v\f]/g;
// eslint-disable-next-line no-control-regex -- matching control characters is the point here
const CONTROLS = /[\x00-\x1f\x7f-\x9f]/g;

/** One display line: ANSI sequences go, line breaks and tabs become spaces; other C0, DEL and C1 controls are dropped. */
export function clean(text: string): string {
  return String(text).replace(ANSI, "").replace(WHITESPACE, " ").replace(CONTROLS, "");
}

const NEWLINES = /\r\n?/g;
const INLINE_WHITESPACE = /[\t\v\f]/g;
// eslint-disable-next-line no-control-regex -- matching control characters is the point here
const CONTROLS_BUT_NEWLINE = /[\x00-\x09\x0b-\x1f\x7f-\x9f]/g;

/** Like `clean`, but keeps line breaks: \r\n and lone \r become \n; tabs, \v and \f become spaces. */
export function cleanMultiline(text: string): string {
  return String(text).replace(ANSI, "").replace(NEWLINES, "\n").replace(INLINE_WHITESPACE, " ").replace(CONTROLS_BUT_NEWLINE, "");
}

const MD_LINK = /\[([^[\]\n]*)\]\(([^()\s]+)\)/g;
const MD_CODE = /`+([^`\n]+)`+/g;
const MD_BOLD = /\*\*([^\s*](?:[^*\n]*[^\s*])?)\*\*/g;

/**
 * Bob's inline Markdown as plain text: ``[`app.py`](app.py:214)`` reads `app.py:214`, `` `code` `` reads `code`,
 * `**bold**` reads `bold`. The result is only ever shown as text: nothing here becomes HTML or a link.
 */
export function plainMarkdown(text: string): string {
  return text
    .replace(MD_LINK, (_match, label: string, target: string) => {
      const name = label.replace(/`/g, "").trim();
      return name === "" || target.startsWith(name) ? target : `${name} (${target})`;
    })
    .replace(MD_CODE, "$1")
    .replace(MD_BOLD, "$1");
}
