import SearchSettings from "../SearchSettings";
import { GROUPS, SWITCHES } from "./copy";
import type { GroupProps } from "./groupProps";
import { isFixed, switchOn, switchPatch } from "./scanPolicy";
import SettingsGroup, { SwitchList } from "./SettingsGroup";
import SwitchRow from "./SwitchRow";

/**
 * Where the scan goes: host, subdomains, robots, what it keeps of each
 * page, and search discovery. The two limits sit with the rule engine in
 * `LimitsGroup`, and Click-Through is a check, so it is under Checks.
 */
export default function CoverageGroup({ settings, update, policy }: GroupProps) {
  const login = policy.mode === "login";

  return (
    <SettingsGroup
      id="coverage"
      legend={GROUPS.coverage.legend}
      description={GROUPS.coverage.description}
      note={policy.fixedNote}
    >
      <SwitchList>
        <SwitchRow
          checked={switchOn(settings, "whole_host")}
          onChange={(on) => update(switchPatch(settings, "whole_host", on))}
          label={login ? SWITCHES.whole_host_login.label : SWITCHES.whole_host.label}
          hint={login ? SWITCHES.whole_host_login.hint : SWITCHES.whole_host.hint}
        />
        {!isFixed(policy, "include_subdomain") && (
          <SwitchRow
            checked={switchOn(settings, "include_subdomain")}
            onChange={(on) => update(switchPatch(settings, "include_subdomain", on))}
            label={SWITCHES.include_subdomain.label}
            hint={SWITCHES.include_subdomain.hint}
          />
        )}
        {!isFixed(policy, "ignore_robots") && (
          <SwitchRow
            tone="warning"
            checked={switchOn(settings, "ignore_robots")}
            onChange={(on) => update(switchPatch(settings, "ignore_robots", on))}
            label={SWITCHES.ignore_robots.label}
            hint={SWITCHES.ignore_robots.hint}
          />
        )}
        {/* What the scan keeps of each page it covers belongs with what it
            covers; it is not a speed setting. Off by default: on means the
            rendered pages are not stored. */}
        <SwitchRow
          checked={switchOn(settings, "skip_rendered_storage")}
          onChange={(on) => update(switchPatch(settings, "skip_rendered_storage", on))}
          disabled={settings.static_only}
          label={SWITCHES.skip_rendered_storage.label}
          hint={settings.static_only ? "A fast scan has no saved copies to keep." : SWITCHES.skip_rendered_storage.hint}
        />
        {/* Search discovery reaches pages only a search box links to, so it
            decides how much of the site is visited. */}
        <div className="px-2 py-2">
          <SearchSettings
            value={settings.search}
            onChange={(search) => update({ search })}
            disabled={settings.static_only || settings.scan_engine === "alfa"}
          />
        </div>
      </SwitchList>
    </SettingsGroup>
  );
}
