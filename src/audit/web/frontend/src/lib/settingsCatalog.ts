/**
 * The settings Axcess offers, with their words: what the Settings page shows,
 * and what Search offers to change straight from its results. The values
 * themselves live in preferences.ts; this is only their labels and choices.
 */
import type { CSSProperties } from "react";
import type { Preferences } from "./preferences";

/**
 * One choice. `preview` draws the label the way the choice looks: a text
 * size at that size, a font in that font. `box` puts a square before the
 * label that grows with the button size it stands for. Both are visual
 * only; the accessible name is still just `label`.
 */
export type Option<V extends string> = { value: V; label: string; preview?: CSSProperties; box?: number };

export interface Setting<K extends keyof Preferences = keyof Preferences> {
  key: K;
  label: string;
  description: string;
  options: ReadonlyArray<Option<Preferences[K]>>;
}

/** Keeps each row's options typed against its own key. */
function setting<K extends keyof Preferences>(row: Setting<K>): Setting {
  return row as unknown as Setting;
}

/*
 * Wording: plain words over measurements and jargon. Options say what the
 * reader gets ("Larger", "Red-weak"), not how it is built ("52 px",
 * "Protan"), the way iOS, Android and Windows name the same settings, and
 * each description says what changes on screen in one or two short
 * sentences. "Default" always marks the setting Axcess starts with.
 */
export const SETTING_SECTIONS: ReadonlyArray<{ id: string; title: string; settings: Setting[] }> = [
  {
    id: "appearance",
    title: "Appearance",
    settings: [
      setting({
        key: "theme",
        label: "Theme",
        description:
          "Dark shows light text on a dark background and is just as easy to read. Match device follows your computer.",
        options: [
          { value: "light", label: "Light" },
          { value: "dark", label: "Dark" },
          { value: "system", label: "Match device" },
        ],
      }),
      setting({
        key: "textSize",
        label: "Text size",
        description: "Makes all text bigger, along with the buttons and boxes around it.",
        options: [
          // The same steps the setting applies to the page: 100%, 112.5%, 125%.
          { value: "100", label: "Default", preview: { fontSize: "1em" } },
          { value: "112", label: "Large", preview: { fontSize: "1.125em" } },
          { value: "125", label: "Larger", preview: { fontSize: "1.25em" } },
        ],
      }),
      setting({
        key: "linkUnderlines",
        label: "Link underlines",
        description: "Underline links all the time so they are easy to spot, not only when you point at them.",
        options: [
          { value: "hover", label: "When pointing" },
          { value: "always", label: "Always" },
        ],
      }),
    ],
  },
  {
    id: "contrast",
    title: "Contrast and color",
    settings: [
      setting({
        key: "contrast",
        label: "Contrast",
        description:
          "Makes gray text and outlines darker. Most uses black text on white with no shaded panels.",
        options: [
          { value: "standard", label: "Default" },
          { value: "more", label: "More" },
          { value: "high", label: "Most" },
        ],
      }),
      setting({
        key: "colorVision",
        label: "Color vision",
        description:
          "Changes colors so they are easier to tell apart if some colors look weak to you, or removes color. Nothing on screen relies on color alone.",
        options: [
          { value: "standard", label: "Default" },
          { value: "protan", label: "Red-weak" },
          { value: "deutan", label: "Green-weak" },
          { value: "tritan", label: "Blue-weak" },
          { value: "grayscale", label: "No color" },
        ],
      }),
    ],
  },
  {
    id: "reading",
    title: "Reading",
    settings: [
      setting({
        key: "font",
        label: "Font",
        description:
          "Clear letters keeps look-alike characters, such as I, l and 1 or O and 0, easy to tell apart.",
        options: [
          { value: "atkinson", label: "Clear letters", preview: { fontFamily: '"Atkinson Hyperlegible Next", sans-serif' } },
          {
            value: "system",
            label: "Device font",
            preview: { fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' },
          },
          { value: "serif", label: "Book style", preview: { fontFamily: 'Charter, "Iowan Old Style", Georgia, serif' } },
        ],
      }),
      setting({
        key: "textSpacing",
        label: "Text spacing",
        description:
          "Adds space between letters, words, lines and paragraphs. Widest uses the spacing from the WCAG text-spacing test.",
        options: [
          { value: "normal", label: "Default" },
          { value: "wide", label: "Wide" },
          { value: "wcag", label: "Widest" },
        ],
      }),
      setting({
        key: "dyslexiaSpacing",
        label: "Extra space in long text",
        description: "More room between words and lines in paragraphs, which many people with dyslexia find easier.",
        options: [
          { value: "off", label: "Off" },
          { value: "on", label: "On" },
        ],
      }),
      setting({
        key: "readingGuide",
        label: "Reading guide",
        description: "A soft band follows your pointer to help you keep your place in long tables.",
        options: [
          { value: "off", label: "Off" },
          { value: "on", label: "On" },
        ],
      }),
    ],
  },
  {
    id: "focus",
    title: "Focus and buttons",
    settings: [
      setting({
        key: "focusIndicator",
        label: "Focus outline",
        description:
          "The outline that shows where you are when you use the keyboard. Bolder adds a thick yellow edge; Bolder, also on click shows it when you use a mouse too.",
        options: [
          { value: "standard", label: "Default" },
          { value: "strong", label: "Bolder" },
          { value: "always", label: "Bolder, also on click" },
        ],
      }),
      setting({
        key: "targetSize",
        label: "Button size",
        description:
          "Makes buttons, links and other controls bigger, so they are easier to click or tap. Default is already large.",
        options: [
          // Squares in the same proportion as the sizes (44, 52 and 60 px).
          { value: "44", label: "Default", box: 0.8 },
          { value: "52", label: "Larger", box: 0.95 },
          { value: "60", label: "Largest", box: 1.1 },
        ],
      }),
      setting({
        key: "tableDensity",
        label: "Table spacing",
        description: "How much room each table row gets. Tight fits more rows on screen; Roomy is easier to follow.",
        options: [
          { value: "compact", label: "Tight" },
          { value: "comfortable", label: "Default" },
          { value: "spacious", label: "Roomy" },
        ],
      }),
    ],
  },
  {
    id: "announcements",
    title: "Screen readers",
    settings: [
      setting({
        key: "announcements",
        label: "Status updates",
        description:
          "When your screen reader reads updates like \u201cSaved\u201d or \u201cPage 2 of 5\u201d: after it finishes what it is saying, right away, or never (they still show on screen). Errors are always read.",
        options: [
          { value: "polite", label: "After a pause" },
          { value: "immediate", label: "Right away" },
          { value: "visual", label: "Show only" },
        ],
      }),
      setting({
        key: "hints",
        label: "Help text",
        description:
          "Short tips that explain a button. Show them when you point at it, under the control whenever you point at it or reach it with the keyboard, or not at all.",
        options: [
          { value: "hover", label: "When pointing" },
          { value: "always", label: "Always" },
          { value: "off", label: "Off" },
        ],
      }),
    ],
  },
  {
    id: "keyboard",
    title: "Keyboard",
    settings: [
      setting({
        key: "shortcuts",
        label: "Keyboard shortcuts",
        description:
          "⌘/Ctrl+K search · ⌘/Ctrl+B sidebar · Alt+1 Reports · Alt+2 About · Alt+3 Settings · ? shortcut list. Turn them off if they get in the way of your screen reader or other tools.",
        options: [
          { value: "on", label: "On" },
          { value: "off", label: "Off" },
        ],
      }),
    ],
  },
  {
    id: "time",
    title: "Time and safety",
    settings: [
      setting({
        key: "messageTiming",
        label: "Message timing",
        description:
          "How long short messages, like \u201cStatus updated\u201d, stay on screen. Longer keeps them five times as long.",
        options: [
          { value: "standard", label: "Default" },
          { value: "extended", label: "Longer" },
          { value: "never", label: "Until I close them" },
        ],
      }),
      setting({
        key: "confirmDelete",
        label: "Ask before deleting",
        description: "Ask \u201cAre you sure?\u201d before a report is deleted, since it cannot be undone.",
        options: [
          { value: "on", label: "On" },
          { value: "off", label: "Off" },
        ],
      }),
    ],
  },
  {
    id: "motion",
    title: "Motion",
    settings: [
      setting({
        key: "motion",
        label: "Animations",
        description:
          "Sliding, fading and other moving effects. Match device follows your computer\u2019s reduce-motion setting; Off stops them all.",
        options: [
          { value: "system", label: "Match device" },
          { value: "on", label: "On" },
          { value: "off", label: "Off" },
        ],
      }),
    ],
  },
  {
    id: "workspace",
    title: "Workspace",
    settings: [
      setting({
        key: "rowsPerPage",
        label: "Rows per page",
        description: "How many rows each table shows before you move to the next page.",
        options: [
          { value: "10", label: "10" },
          { value: "25", label: "25" },
          { value: "50", label: "50" },
        ],
      }),
      setting({
        key: "sidebar",
        label: "Sidebar",
        description: "Open shows a name beside each icon. Icons only keeps the sidebar narrow.",
        options: [
          { value: "open", label: "Open" },
          { value: "collapsed", label: "Icons only" },
        ],
      }),
    ],
  },
];

/**
 * Every setting in the order the Settings page shows them, with the title of
 * the section it sits in. Search (the command palette) lists them so a
 * setting can be changed from its results, without opening Settings.
 */
export const ALL_SETTINGS: ReadonlyArray<Setting & { section: string }> = SETTING_SECTIONS.flatMap((section) =>
  section.settings.map((row) => ({ ...row, section: section.title })),
);
