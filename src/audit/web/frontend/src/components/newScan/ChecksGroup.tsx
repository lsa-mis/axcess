import SearchSettings from "../SearchSettings";
import { ENGINE, GROUPS, STANDARD, SWITCHES } from "./copy";
import type { GroupProps } from "./groupProps";
import PillGroup from "./PillGroup";
import { isFixed, switchOn, switchPatch, type ScanSettings, type SwitchKey } from "./scanPolicy";
import SettingsGroup from "./SettingsGroup";
import SwitchRow from "./SwitchRow";

/** How many of the check switches are on, for the disclosure header. */
export function checksCount(settings: ScanSettings, policy: GroupProps["policy"]) {
  const keys: SwitchKey[] = ["keyboard", "focus", "responsive"];
  const shown = keys.filter((key) => !(key === "focus" && isFixed(policy, "skip_focus")));
  return { on: shown.filter((key) => switchOn(settings, key)).length, total: shown.length };
}

/**
 * What each page is tested for: the standard, the rule engine, and the
 * browser checks that need a rendered page. The search-discovery settings
 * belong here too: they exist so that pages only reachable through a
 * search box get checked at all.
 */
export default function ChecksGroup({ settings, update, policy, capabilities }: GroupProps) {
  const alfaOff = capabilities.alfa?.available === false;
  const alfaReason = alfaOff
    ? `Siteimprove Alfa is unavailable: ${capabilities.alfa?.reason ?? "not installed"}.`
    : undefined;
  const rendered = !settings.static_only;

  return (
    <SettingsGroup id="checks" legend={GROUPS.checks.legend} description={GROUPS.checks.description}>
      <div className="grid gap-5 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
        <PillGroup
          name="axe-level"
          label={STANDARD.label}
          hint={STANDARD.hint}
          value={settings.axe_level}
          onChange={(axe_level) => update({ axe_level })}
          options={[
            { value: "A", label: "A" },
            { value: "AA", label: "AA" },
            { value: "AAA", label: "AAA" },
          ]}
        />
        <PillGroup
          name="scan-engine"
          label={ENGINE.label}
          hint={alfaReason}
          value={settings.scan_engine}
          onChange={(scan_engine) => {
            const patch: Partial<ScanSettings> = { scan_engine };
            // Alfa alone cannot re-check revealed content; axe or Both
            // cannot run without a rendered page.
            if (scan_engine === "alfa") patch.skip_interaction = true;
            else if (settings.static_only) patch.static_only = false;
            update(patch);
          }}
          options={[
            { value: "axe", label: ENGINE.axe.label, hint: ENGINE.axe.hint },
            { value: "alfa", label: ENGINE.alfa.label, hint: ENGINE.alfa.hint, disabled: alfaOff },
            { value: "both", label: ENGINE.both.label, hint: ENGINE.both.hint, disabled: alfaOff },
          ]}
        />
      </div>

      <div className="-mx-2 grid gap-x-4 border-t border-border pt-4 sm:grid-cols-2">
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
      </div>

      <div className="-mx-2 border-t border-border pt-4">
        <SearchSettings
          value={settings.search}
          onChange={(search) => update({ search })}
          disabled={settings.static_only || settings.scan_engine === "alfa"}
        />
      </div>
    </SettingsGroup>
  );
}
