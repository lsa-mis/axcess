import { GROUPS, NUMBERS, SWITCHES } from "./copy";
import type { GroupProps } from "./groupProps";
import NumberField from "./NumberField";
import { isFixed, switchOn, switchPatch } from "./scanPolicy";
import SettingsGroup from "./SettingsGroup";
import SwitchRow from "./SwitchRow";

/**
 * How hard the crawler works and whether you can watch it. Fast crawl lives
 * here rather than under Coverage because it is a speed trade, and it is the
 * one switch that can make the form refuse to start: the conflict with
 * axe-core is shown on the switch itself, not only in the alert at the end.
 */
export default function SpeedGroup({ settings, update, policy, errors, fieldIds }: GroupProps) {
  const login = policy.mode === "login";
  const staticError = errors.find((error) => error.field === "static_only")?.message;

  return (
    <SettingsGroup id="speed" legend={GROUPS.speed.legend} description={GROUPS.speed.description}>
      <div className="flex flex-wrap gap-x-5 gap-y-3">
        <NumberField
          label={NUMBERS.rps.label}
          hint={NUMBERS.rps.hint}
          value={settings.rps}
          min={0.1}
          max={policy.caps.rps}
          step={0.1}
          onChange={(value) => update({ rps: value })}
          className="w-64"
        />
        <NumberField
          label={login ? NUMBERS.workers_login.label : NUMBERS.workers.label}
          hint={login ? NUMBERS.workers_login.hint : NUMBERS.workers.hint}
          value={settings.workers}
          min={1}
          max={policy.caps.workers}
          onChange={(value) => update({ workers: value })}
          className="w-64"
        />
      </div>
      <div className="-mx-2 grid gap-x-4 border-t border-border pt-4 sm:grid-cols-2">
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
                  ? "There is no browser to show during a Fast crawl."
                  : SWITCHES.show_browser.hint
              }
            />
          )}
      </div>
    </SettingsGroup>
  );
}
