import SearchSettings from "../SearchSettings";
import { ALL_PAGES, GROUPS, NUMBERS, SWITCHES } from "./copy";
import type { GroupProps } from "./groupProps";
import NumberField from "./NumberField";
import { isFixed, LIMIT_MIN, switchOn, switchPatch } from "./scanPolicy";
import SettingsGroup, { SwitchList } from "./SettingsGroup";
import SwitchRow from "./SwitchRow";

/**
 * Where the scan goes and how far: host, subdomains, robots, what it keeps
 * of each page, search discovery, then the limits (scan every page it
 * finds, maximum pages, maximum link depth). Click-Through is a check, so it
 * is under Checks.
 *
 * The limits joined this group on 2026-11-02, from "Limits and rule check
 * tool" (see ScanForm). They come last: first which pages are in reach, then
 * how many of them to visit. Each limit states its range in its own
 * description, and a value out of range is named beside the field as well
 * as in the alert at the top of the form, which opens this group so the
 * alert's link lands on a visible field (ScanForm, GROUP_FIELDS).
 */
export default function CoverageGroup({ settings, update, policy, errors, fieldIds }: GroupProps) {
  const login = policy.mode === "login";
  const errorFor = (field: "max_pages" | "max_depth") => errors.find((error) => error.field === field)?.message;
  const offersAllPages = !isFixed(policy, "all_pages");
  const allPages = offersAllPages && settings.all_pages;

  return (
    <SettingsGroup
      id="coverage"
      variant="plain"
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
        {offersAllPages && (
          <SwitchRow
            tone="warning"
            checked={allPages}
            onChange={(on) => update({ all_pages: on })}
            label={ALL_PAGES.label}
            hint={ALL_PAGES.hint}
          />
        )}
      </SwitchList>
      <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
        <NumberField
          id={fieldIds.max_pages}
          label={NUMBERS.max_pages.label}
          hint={allPages ? ALL_PAGES.maxPagesOff : NUMBERS.max_pages.hint(policy.caps.max_pages)}
          error={allPages ? undefined : errorFor("max_pages")}
          disabled={allPages}
          value={settings.max_pages}
          min={LIMIT_MIN}
          max={policy.caps.max_pages}
          step={1}
          onChange={(value) => update({ max_pages: value })}
          inputClassName="w-36"
        />
        <NumberField
          id={fieldIds.max_depth}
          label={NUMBERS.max_depth.label}
          hint={NUMBERS.max_depth.hint(policy.caps.max_depth)}
          error={errorFor("max_depth")}
          value={settings.max_depth}
          min={LIMIT_MIN}
          max={policy.caps.max_depth}
          step={1}
          onChange={(value) => update({ max_depth: value })}
          inputClassName="w-36"
        />
      </div>
    </SettingsGroup>
  );
}
