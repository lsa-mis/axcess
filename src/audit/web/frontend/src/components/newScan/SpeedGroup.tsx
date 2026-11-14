import { Select } from "../ui";
import { GROUPS, NUMBERS, SWITCHES, USER_AGENT } from "./copy";
import type { GroupProps } from "./groupProps";
import NumberField from "./NumberField";
import { isFixed, switchOn, switchPatch } from "./scanPolicy";
import SettingsGroup, { SwitchList } from "./SettingsGroup";
import SwitchRow from "./SwitchRow";
import TextField from "./TextField";
import {
  CUSTOM_USER_AGENT_CHOICE,
  DEFAULT_USER_AGENT_CHOICE,
  presetFor,
  USER_AGENT_PRESETS,
} from "./userAgents";

const USER_AGENT_OPTIONS = [
  { value: DEFAULT_USER_AGENT_CHOICE, label: USER_AGENT.defaultOption },
  ...USER_AGENT_PRESETS.map((preset) => ({ value: preset.id, label: preset.label })),
  { value: CUSTOM_USER_AGENT_CHOICE, label: USER_AGENT.customOption },
];

/**
 * How hard the crawler works and whether you can watch it. Fast crawl lives
 * here rather than under Coverage because it is a speed trade, and it is the
 * one switch that can make the form refuse to start: the conflict with
 * axe-core is shown on the switch itself, not only in the alert at the end.
 *
 * It renders inside the "Speed and browser window" disclosure, which already
 * shows its name, so the fieldset is `plain` and its legend is for a screen
 * reader only.
 *
 * The browser the site sees (user agent) is last, after the switches about
 * the browser window: it is a browser setting too, and it is the one most
 * people never change. One shared `Select` lists Axcess's own name first
 * (the default), then current browsers by name and device, then "Type your
 * own…", which shows a text box under it. Rejected: a text box with a list
 * of suggestions (`<input list>` and `<datalist>`), which would put "type or
 * pick" into one control, but screen readers announce its suggestions
 * unevenly, and each suggestion would be a 120-character string, not a
 * name. Rejected too: a radio group, which is ten rows for a setting that is
 * usually left alone (W3C COGA, "Making Content Usable": keep the page
 * simple, paraphrased; https://www.w3.org/TR/coga-usable/).
 *
 * The exact string a choice sends is shown under it, so a developer can
 * check it without opening developer tools; it is text, not a control.
 * A sign-in scan pins the choice to Axcess's own name (LOGIN_POLICY), so
 * the control is not shown there.
 */
export default function SpeedGroup({ settings, update, policy, errors, fieldIds }: GroupProps) {
  const login = policy.mode === "login";
  const staticError = errors.find((error) => error.field === "static_only")?.message;
  const userAgentError = errors.find((error) => error.field === "user_agent")?.message;
  const preset = presetFor(settings.user_agent_choice);

  return (
    <SettingsGroup
      id="speed"
      variant="plain"
      legend={GROUPS.speed.legend}
      description={GROUPS.speed.description}
    >
      <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
        <NumberField
          label={NUMBERS.rps.label}
          hint={NUMBERS.rps.hint}
          value={settings.rps}
          min={0.1}
          max={policy.caps.rps}
          step={0.1}
          onChange={(value) => update({ rps: value })}
          inputClassName="w-36"
        />
        {/* One name on both forms, "Pages at once (workers)": to the person
            it is the same choice, how many pages are worked on at the same
            time. A sign-in scan does that with signed-in browser tabs and a
            public scan with a fresh window per page, but that is how it
            works, not what the person decides. It used to be "Signed-in
            tabs" here, a second name for one setting (W3C COGA, "Making
            Content Usable": use the same word for the same thing,
            paraphrased; https://www.w3.org/TR/coga-usable/; and SC 3.2.4
            Consistent Identification, Level AA). The hint differs, because
            the numbers and the sign-out limit do. */}
        <NumberField
          label={NUMBERS.workers.label}
          hint={login ? NUMBERS.workers_login.hint : NUMBERS.workers.hint}
          value={settings.workers}
          min={1}
          max={policy.caps.workers}
          onChange={(value) => update({ workers: value })}
          inputClassName="w-36"
        />
      </div>
      <SwitchList>
        {!isFixed(policy, "static_only") && (
          <SwitchRow
            id={fieldIds.static_only}
            tone="warning"
            checked={switchOn(settings, "static_only")}
            onChange={(on) => update(switchPatch(settings, "static_only", on))}
            label={SWITCHES.static_only.label}
            hint={SWITCHES.static_only.hint}
            error={staticError}
          />
        )}
        {!isFixed(policy, "show_browser") && (
          <SwitchRow
            checked={switchOn(settings, "show_browser")}
            onChange={(on) => update(switchPatch(settings, "show_browser", on))}
            disabled={settings.static_only}
            label={SWITCHES.show_browser.label}
            hint={
              settings.static_only
                ? "A fast scan does not use a browser, so there is nothing to show."
                : SWITCHES.show_browser.hint
            }
          />
        )}
      </SwitchList>
      {!isFixed(policy, "user_agent_choice") && (
        <div className="flex min-w-0 flex-col gap-3">
          <Select
            id="scan-user-agent-choice"
            label={USER_AGENT.label}
            stacked
            hint={USER_AGENT.hint}
            value={settings.user_agent_choice}
            onChange={(value) => update({ user_agent_choice: value })}
            options={USER_AGENT_OPTIONS}
          />
          {settings.user_agent_choice === CUSTOM_USER_AGENT_CHOICE ? (
            <TextField
              id={fieldIds.user_agent}
              label={USER_AGENT.customLabel}
              hint={USER_AGENT.customHint}
              value={settings.user_agent}
              onChange={(value) => update({ user_agent: value })}
              error={userAgentError}
            />
          ) : preset ? (
            <div className="flex flex-col gap-1 text-xs text-fg-muted">
              <p>
                {USER_AGENT.sends} <code className="break-all font-mono text-fg">{preset.value}</code>
              </p>
              {preset.phone && <p>{USER_AGENT.phone}</p>}
            </div>
          ) : (
            <p className="text-xs text-fg-muted">{USER_AGENT.sendsDefault}</p>
          )}
        </div>
      )}
    </SettingsGroup>
  );
}
