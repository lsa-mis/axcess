import { CLICK_THROUGH_COPY, GROUPS, STANDARD, SWITCHES, WCAG_VERSION } from "./copy";
import type { GroupProps } from "./groupProps";
import PillGroup from "./PillGroup";
import { isFixed, switchOn, switchPatch } from "./scanPolicy";
import SettingsGroup, { SwitchList } from "./SettingsGroup";
import SwitchRow from "./SwitchRow";

/**
 * What each page is tested for: the standard (level and WCAG version),
 * Click-Through, and the browser checks that need a rendered page. The rule
 * engine is chosen beside the limits, in `LimitsGroup`.
 */
export default function ChecksGroup({ settings, update, policy }: GroupProps) {
  const rendered = !settings.static_only;
  const clickThroughBlocked = settings.static_only
    ? CLICK_THROUGH_COPY.unavailableStatic
    : settings.scan_engine === "alfa"
      ? CLICK_THROUGH_COPY.unavailableAlfa
      : null;

  return (
    <SettingsGroup id="checks" legend={GROUPS.checks.legend} description={GROUPS.checks.description}>
      <div className="grid gap-5 sm:grid-cols-2">
        <PillGroup
          name="axe-level"
          label={STANDARD.label}
          hint={STANDARD.hint(settings.wcag_version)}
          value={settings.axe_level}
          onChange={(axe_level) => update({ axe_level })}
          options={[
            { value: "A", label: "A" },
            { value: "AA", label: "AA" },
            { value: "AAA", label: "AAA" },
          ]}
        />
        <PillGroup
          name="wcag-version"
          label={WCAG_VERSION.label}
          hint={WCAG_VERSION.hint}
          value={settings.wcag_version}
          onChange={(wcag_version) => update({ wcag_version })}
          options={[
            { value: "2.1", label: "2.1" },
            { value: "2.2", label: "2.2" },
          ]}
        />
      </div>

      <SwitchList>
        <SwitchRow
          checked={switchOn(settings, "click_through")}
          onChange={(on) => update(switchPatch(settings, "click_through", on))}
          disabled={clickThroughBlocked !== null}
          label={SWITCHES.click_through.label}
          hint={clickThroughBlocked ?? SWITCHES.click_through.hint}
        />
        <SwitchRow
          checked={switchOn(settings, "keyboard")}
          onChange={(on) => update(switchPatch(settings, "keyboard", on))}
          disabled={!rendered}
          label={SWITCHES.keyboard.label}
          hint={rendered ? SWITCHES.keyboard.hint : "Needs a rendered page; turn off Fast crawl."}
        />
        {!isFixed(policy, "skip_focus") && (
          <SwitchRow
            checked={switchOn(settings, "focus")}
            onChange={(on) => update(switchPatch(settings, "focus", on))}
            disabled={!rendered}
            label={SWITCHES.focus.label}
            hint={rendered ? SWITCHES.focus.hint : "Needs a rendered page; turn off Fast crawl."}
          />
        )}
        <SwitchRow
          checked={switchOn(settings, "responsive")}
          onChange={(on) => update(switchPatch(settings, "responsive", on))}
          disabled={!rendered}
          label={SWITCHES.responsive.label}
          hint={rendered ? SWITCHES.responsive.hint : "Needs a rendered page; turn off Fast crawl."}
        />
      </SwitchList>
    </SettingsGroup>
  );
}
