import { ALL_PAGES, ENGINE, GROUPS, NUMBERS } from "./copy";
import { CHECK_LABEL } from "../../lib/terms";
import type { GroupProps } from "./groupProps";
import NumberField from "./NumberField";
import PillGroup from "./PillGroup";
import { isFixed, LIMIT_MIN, type ScanSettings } from "./scanPolicy";
import SettingsGroup, { SwitchList } from "./SettingsGroup";
import SwitchRow from "./SwitchRow";

/**
 * When the scan stops and which engine checks each page. Each limit states
 * its range in its own description, and a value out of range is named
 * beside the field as well as in the alert at the top of the form. The
 * group is always open, so the alert's links always land on a visible
 * field.
 */
export default function LimitsGroup({ settings, update, policy, capabilities, errors, fieldIds }: GroupProps) {
  const errorFor = (field: "max_pages" | "max_depth") => errors.find((error) => error.field === field)?.message;
  const alfaOff = capabilities.alfa?.available === false;
  const alfaReason = alfaOff
    ? `${CHECK_LABEL.alfa} is not available: ${capabilities.alfa?.reason ?? "not installed"}.`
    : undefined;

  const offersAllPages = !isFixed(policy, "all_pages");
  const allPages = offersAllPages && settings.all_pages;

  return (
    <SettingsGroup variant="plain" id="limits" legend={GROUPS.limits.legend}>
      {offersAllPages && (
        <SwitchList>
          <SwitchRow
            tone="warning"
            checked={allPages}
            onChange={(on) => update({ all_pages: on })}
            label={ALL_PAGES.label}
            hint={ALL_PAGES.hint}
          />
        </SwitchList>
      )}
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
    </SettingsGroup>
  );
}
