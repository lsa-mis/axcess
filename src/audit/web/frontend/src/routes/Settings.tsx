import { useId, useState } from "react";
import { Check, RotateCcw } from "lucide-react";
import { Button, Card, PageHeader } from "../components/ui";
import { cn } from "../lib/cn";
import { PRESETS, presetIsOn, presetOffValues, type Preferences } from "../lib/preferences";
import { SETTING_SECTIONS, type Setting } from "../lib/settingsCatalog";
import {
  resetPreferences,
  setPreference,
  updatePreferences,
  usePreferences,
} from "../hooks/usePreferences";

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
          {/* The explanation above and the presets on a row of their own, so all
              four sit on one line instead of wrapping beside the text. */}
          <div className="flex flex-col gap-3 px-4 py-4">
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
                    {/* eslint-disable-next-line react/forbid-elements -- Keep: a preset toggle pill (aria-pressed); there is no shared toggle-pill component */}
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

        {SETTING_SECTIONS.map((section) => (
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
        <p id={`${id}-desc`} className="mt-0.5 text-xs text-fg-muted">
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
                "relative inline-flex min-h-target min-w-target cursor-pointer items-center justify-center whitespace-nowrap rounded-2xs border px-3 text-xs font-semibold transition-colors motion-reduce:transition-none",
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
                // label is the radio's own 44 px hit area, in both directions
                // (min-w-target too: a two-character option such as "On" was
                // 41 px wide; SC 2.5.5 Target Size (Enhanced), Level AAA).
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
