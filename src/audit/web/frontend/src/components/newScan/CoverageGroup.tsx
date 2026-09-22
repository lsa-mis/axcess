import { GROUPS, NUMBERS, SWITCHES } from "./copy";
import type { GroupProps } from "./groupProps";
import NumberField from "./NumberField";
import { isFixed, switchField, switchOn, switchPatch, type SwitchKey } from "./scanPolicy";
import SettingsGroup from "./SettingsGroup";
import SwitchRow from "./SwitchRow";

/** How many switches in this group are on, for the disclosure header. */
export function coverageCount(settings: GroupProps["settings"], policy: GroupProps["policy"]) {
  const keys: SwitchKey[] = ["whole_host", "include_subdomain", "ignore_robots", "click_through"];
  const shown = keys.filter((key) => !isFixed(policy, switchField(key)));
  return { on: shown.filter((key) => switchOn(settings, key)).length, total: shown.length };
}

/**
 * Where the scan goes: host, subdomains, robots, click-through, and the
 * two limits. The depth limit gets a strip of dots, one per click from the
 * start page, because "10" on its own reads as arbitrary and ten filled
 * dots reads as "most of the site".
 */
export default function CoverageGroup({ settings, update, policy, capabilities }: GroupProps) {
  const login = policy.mode === "login";
  const clickThroughBlocked = settings.static_only
    ? "Unavailable with Fast crawl: opening controls needs a rendered page."
    : settings.scan_engine === "alfa"
      ? "Choose axe-core or Both: revealed content is re-checked with axe-core."
      : null;
  void capabilities;
  const depth = Math.max(0, Math.min(10, Math.round(settings.max_depth)));

  return (
    <SettingsGroup
      id="coverage"
      legend={GROUPS.coverage.legend}
      description={GROUPS.coverage.description}
      note={policy.fixedNote}
    >
      <div className="-mx-2 grid gap-x-4 sm:grid-cols-2">
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
        <SwitchRow
          checked={switchOn(settings, "click_through")}
          onChange={(on) => update(switchPatch(settings, "click_through", on))}
          disabled={clickThroughBlocked !== null}
          label={SWITCHES.click_through.label}
          hint={clickThroughBlocked ?? SWITCHES.click_through.hint}
        />
        {/* What the scan keeps of each page it covers belongs with what it
            covers; it is not a speed setting. Off by default: on means the
            rendered pages are not stored. Not in the header count, which
            tallies what the scan does, not what it leaves out. */}
        <SwitchRow
          checked={switchOn(settings, "skip_rendered_storage")}
          onChange={(on) => update(switchPatch(settings, "skip_rendered_storage", on))}
          disabled={settings.static_only}
          label={SWITCHES.skip_rendered_storage.label}
          hint={settings.static_only ? "A Fast crawl has no rendered pages to store." : SWITCHES.skip_rendered_storage.hint}
        />
      </div>

      <div className="flex flex-wrap items-end gap-x-5 gap-y-3 border-t border-border pt-4">
        <NumberField
          label={NUMBERS.max_pages.label}
          value={settings.max_pages}
          min={1}
          max={policy.caps.max_pages}
          onChange={(value) => update({ max_pages: value })}
          className="w-36"
        />
        <NumberField
          label={NUMBERS.max_depth.label}
          value={settings.max_depth}
          min={1}
          max={policy.caps.max_depth}
          onChange={(value) => update({ max_depth: value })}
          className="w-36"
        />
        <div className="flex flex-col gap-1.5 pb-2">
          <span className="text-xs text-fg-muted">{NUMBERS.max_depth.hint}</span>
          <div className="flex items-center gap-1.5" aria-hidden>
            {Array.from({ length: 10 }, (_, index) => (
              <span
                key={index}
                className={
                  index < depth
                    ? "h-3.5 w-3.5 scale-110 rounded-full bg-umich-blue transition-[background-color,transform] duration-200 motion-reduce:transition-none"
                    : "h-3.5 w-3.5 rounded-full bg-border transition-[background-color,transform] duration-200 motion-reduce:transition-none"
                }
              />
            ))}
            {settings.max_depth > 10 && (
              <span className="ml-1 text-xs font-semibold text-fg-muted">+{settings.max_depth - 10}</span>
            )}
          </div>
        </div>
      </div>
    </SettingsGroup>
  );
}
