const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

// Guardrails for the Windows installer's words (installer/installer.nsh),
// from docs/plain-language.md: sentence case for everything (rule 11), no
// "please" (rule 11), and "choose", the word the app uses, not "click".

const root = path.resolve(__dirname, "..");
const script = fs.readFileSync(path.join(root, "installer", "installer.nsh"), "utf8");

/** Every `LangString <name> ${LANG_ENGLISH} "<text>"` in the file, as [name, text]. */
function langStrings(source) {
  const found = [];
  for (const match of source.matchAll(/^\s*LangString\s+(\S+)\s+\$\{LANG_ENGLISH\}\s+"((?:[^"\\]|\\.)*)"\s*$/gm)) {
    found.push([match[1], match[2]]);
  }
  return found;
}

/** The words a person sees: NSIS line breaks and variables out, & shortcut markers out. */
function visible(text) {
  return text
    .replace(/\$\\r\$\\n/g, "\n")
    .replace(/\$\{[^}]+\}/g, "0.2.3")
    .replace(/\$_CLICK/g, "")
    .replace(/\$(INSTDIR|0)/g, "C:\\Folder")
    .replace(/&/g, "");
}

// Words that keep their capital inside a sentence: names, and the labels
// of buttons and choices a message tells you to pick ("choose Retry").
// A new entry needs the same reason; a Title Case label does not belong.
const CAPITALIZED = new Set([
  "Axcess",
  "Windows",
  "Settings",
  "Apps",
  "Start",
  "APPDATA",
  // Button and choice labels named in the text.
  "OK",
  "Cancel",
  "Retry",
  "Ignore",
  "Abort",
  "Install",
  "Uninstall",
  "Next",
  "Browse",
  "Finish",
  "Only",
]);

/**
 * Words written with a capital where sentence case has none: any word that
 * is not the first of a sentence, a line, or a label list, and is not an
 * allowed name or label. "Choose Installation Options" returns
 * ["Installation", "Options"].
 */
function titleCaseWords(text) {
  const wrong = [];
  for (const line of text.split("\n")) {
    const words = line.split(/\s+/).filter(Boolean);
    words.forEach((word, index) => {
      const bare = word.replace(/^[("'<]+|[)"'.,:;?!>]+$/g, "");
      if (!/^[A-Z][a-z]/.test(bare)) return;
      const previous = index === 0 ? "" : words[index - 1];
      const startsSentence = index === 0 || /[.?!:]$/.test(previous);
      if (startsSentence || CAPITALIZED.has(bare) || bare.includes("\\")) return;
      wrong.push(bare);
    });
  }
  return wrong;
}

const strings = langStrings(script);

test("the installer wording file defines its strings", () => {
  assert.ok(strings.length > 60, `only ${strings.length} strings found; is the LangString pattern still right?`);
});

test("installer text is in sentence case", () => {
  const failures = strings
    .map(([name, text]) => [name, titleCaseWords(visible(text))])
    .filter(([, words]) => words.length > 0)
    .map(([name, words]) => `${name}: ${words.join(", ")}`);
  assert.deepEqual(failures, [], `Title Case words in installer text:\n${failures.join("\n")}`);
});

test("every installer string starts with a capital letter", () => {
  const failures = strings.filter(([, text]) => !/^[A-Z0-9<]/.test(visible(text).trim()));
  assert.deepEqual(failures.map(([name]) => name), []);
});

test("installer text never says please or click", () => {
  const failures = strings.filter(([, text]) => /\b(please|click)\b/i.test(visible(text)));
  assert.deepEqual(failures.map(([name]) => name), []);
});

test("the sentence-case check catches Title Case", () => {
  assert.deepEqual(titleCaseWords("Choose Installation Options"), ["Installation", "Options"]);
  assert.deepEqual(titleCaseWords("Only For Me"), ["For", "Me"]);
  assert.deepEqual(titleCaseWords("Open Axcess now"), []);
  assert.deepEqual(titleCaseWords("Close Axcess, then choose Retry. Choose Cancel to stop."), []);
});

// electron-builder's own messages are English defaults written for any app.
// Each one must be replaced here, so an electron-builder upgrade that adds
// a message fails this test instead of shipping it unreviewed.
const templates = path.join(root, "node_modules", "app-builder-lib", "templates", "nsis");

test("every electron-builder installer message is replaced", { skip: !fs.existsSync(templates) }, () => {
  const replaced = new Set(strings.map(([name]) => name));
  const missing = [];
  for (const file of ["messages.yml", "assistedMessages.yml"]) {
    const source = fs.readFileSync(path.join(templates, file), "utf8");
    for (const match of source.matchAll(/^([A-Za-z0-9_]+):\s*$/gm)) {
      if (!replaced.has(match[1])) missing.push(`${file}: ${match[1]}`);
    }
  }
  assert.deepEqual(missing, [], `Not replaced in installer/installer.nsh:\n${missing.join("\n")}`);
});

module.exports = { titleCaseWords };
