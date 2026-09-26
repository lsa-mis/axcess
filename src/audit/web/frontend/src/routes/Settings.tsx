import { useId, useState, type CSSProperties } from "react";
import { Check, RotateCcw } from "lucide-react";
import { Button, Card, PageHeader } from "../components/ui";
import { cn } from "../lib/cn";
import { PRESETS, presetIsOn, presetOffValues, type Preferences } from "../lib/preferences";
import {
  resetPreferences,
  setPreference,
  updatePreferences,
  usePreferences,
} from "../hooks/usePreferences";

/**
 * One choice. `preview` draws the label the way the choice looks: a text
 * size at that size, a font in that font. `box` puts a square before the
 * label that grows with the button size it stands for. Both are visual
 * only; the accessible name is still just `label`.
 */
type Option<V extends string> = { value: V; label: string; preview?: CSSProperties; box?: number };

interface Setting<K extends keyof Preferences = keyof Preferences> {
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
const SECTIONS: ReadonlyArray<{ id: string; title: string; settings: Setting[] }> = [
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
 * Display and behaviour preferences for this computer.
 *
 * Every change applies the moment it is chosen: there is no Save button to
 * miss, and nothing here is sent to the server. Each setting is a native
 * radio group, so arrow keys move between its options and a screen reader
 * hears the group's name and description before the choice.
 */
export default function SettingsRoute() {
  const prefs = usePreferences();
  const [message, setMessage] = useState("");

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Settings"
        subtitle="Saved on this computer and applied right away."
        actions={
          <Button
            type="button"
            onClick={() => {
              resetPreferences();
              setMessage("Settings reset to defaults.");
            }}
          >
            <RotateCcw className="h-4 w-4" aria-hidden />
            Reset to defaults
          </Button>
        }
      />
      {/* Always in the DOM so the first message is announced, not just shown. */}
      <p role="status" className={cn("text-sm font-semibold text-fg", message ? "mb-4" : "sr-only")}>
        {message}
      </p>

      <div className="space-y-5">
        <Card className="border-l-4 border-l-umich-blue">
          <div className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-fg">Quick presets</h2>
              <p className="mt-0.5 text-xs text-fg-muted">
                Turn on a starting set of options, then fine-tune below. Select an active preset again to turn it off.
              </p>
            </div>
            <ul className="flex flex-wrap gap-2" aria-label="Quick presets">
              {PRESETS.map((preset) => {
                const on = presetIsOn(prefs, preset);
                return (
                  <li key={preset.id}>
                    {/* A toggle: aria-pressed says on or off, and the tick
                        and filled pill show it without relying on colour. */}
                    <button
                      type="button"
                      aria-pressed={on}
                      onClick={() => {
                        if (on) {
                          updatePreferences(presetOffValues(prefs, preset));
                          setMessage(`${preset.label} preset turned off. Its settings are back to their defaults.`);
                        } else {
                          updatePreferences(preset.values);
                          setMessage(`${preset.label} preset applied.`);
                        }
                      }}
                      className={cn(
                        "inline-flex min-h-target items-center gap-1.5 rounded-full border px-3.5 text-xs font-semibold transition-colors",
                        on
                          ? "border-umich-blue bg-umich-blue text-fg-inverse hover:bg-umich-blue-600"
                          : "border-border-strong bg-surface text-fg hover:border-umich-blue hover:bg-surface-muted",
                      )}
                    >
                      {on && <Check className="h-3.5 w-3.5" aria-hidden />}
                      {preset.label}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </Card>

        {SECTIONS.map((section) => (
          <Card key={section.id} className="overflow-hidden">
            <section aria-labelledby={`settings-${section.id}`}>
              <h2
                id={`settings-${section.id}`}
                className="border-b border-border bg-surface-muted px-4 py-3 text-sm font-semibold text-fg"
              >
                {section.title}
              </h2>
              <div className="divide-y divide-border">
                {section.settings.map((row) => (
                  <SettingRow
                    key={row.key}
                    row={row}
                    value={prefs[row.key]}
                    onChange={(value) => setPreference(row.key, value)}
                  />
                ))}
              </div>
            </section>
          </Card>
        ))}
      </div>
    </div>
  );
}

function SettingRow({
  row,
  value,
  onChange,
}: {
  row: Setting;
  value: string;
  onChange: (value: Preferences[keyof Preferences]) => void;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-3 px-4 py-3 xl:flex-row xl:items-center xl:justify-between xl:gap-8">
      <div className="min-w-0">
        <p id={`${id}-label`} className="text-sm font-semibold text-fg">
          {row.label}
        </p>
        <p id={`${id}-desc`} className="mt-0.5 text-xs leading-5 text-fg-muted">
          {row.description}
        </p>
      </div>
      <div
        role="radiogroup"
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-desc`}
        className="inline-flex shrink-0 flex-wrap gap-1 self-start rounded-xs border border-border bg-surface-muted p-1 xl:self-auto"
      >
        {row.options.map((option) => {
          const selected = option.value === value;
          return (
            <label
              key={option.value}
              className={cn(
                "relative inline-flex min-h-target cursor-pointer items-center justify-center whitespace-nowrap rounded-2xs border px-3 text-xs font-semibold transition-colors motion-reduce:transition-none",
                // Chosen is a raised white card with a border: a change of
                // shape and weight, not only of colour.
                selected
                  ? "border-border-strong bg-surface text-umich-blue shadow-sm"
                  : "border-transparent text-fg-muted hover:bg-surface hover:text-fg",
                "has-[:focus-visible]:outline has-[:focus-visible]:outline-[3px] has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-umich-blue",
              )}
            >
              <input
                type="radio"
                name={id}
                value={option.value}
                checked={selected}
                onChange={() => onChange(option.value)}
                // Covers the whole option, invisible, like PillGroup: the
                // label is the radio's own 44 px hit area.
                className="absolute inset-0 m-0 h-full w-full cursor-[inherit] appearance-none rounded-2xs opacity-0"
              />
              {option.box !== undefined && (
                <span
                  aria-hidden
                  className="mr-1.5 shrink-0 rounded-[3px] border-[1.5px] border-current"
                  style={{ width: `${option.box}em`, height: `${option.box}em` }}
                />
              )}
              <span style={option.preview}>{option.label}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}
