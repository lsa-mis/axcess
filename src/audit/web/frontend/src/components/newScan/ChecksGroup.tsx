import { CLICK_THROUGH_COPY, ENGINE, FORMS_CHOICE, GROUPS, STANDARD, SWITCHES, WCAG_VERSION } from "./copy";
import { CHECK_LABEL } from "../../lib/terms";
import type { GroupProps } from "./groupProps";
import PillGroup from "./PillGroup";
import { isFixed, switchOn, switchPatch, type ScanSettings } from "./scanPolicy";
import SettingsGroup, { SwitchList } from "./SettingsGroup";
import SwitchRow from "./SwitchRow";

/**
 * What each page is tested for and with what: the standard (level and WCAG
 * version), the rule check tool, Click-Through, and the browser checks that
 * need a rendered page.
 *
 * The rule check tool joined this group on 2026-11-02, from "Limits and
 * rule check tool" (see ScanForm): which tool checks the pages is part of
 * what Axcess tests on each page, this group's own description. It sits
 * under the standard it checks against, before the switches that add
 * checks of their own, and it decides whether Click-Through can run (Alfa
 * alone cannot), so the switch it disables is right below it.
 */
export default function ChecksGroup({ settings, update, policy, capabilities }: GroupProps) {
  const rendered = !settings.static_only;
  const alfaOff = capabilities.alfa?.available === false;
  const alfaReason = alfaOff
    ? `${CHECK_LABEL.alfa} is not available: ${capabilities.alfa?.reason ?? "not installed"}.`
    : undefined;
  const clickThroughBlocked = settings.static_only
    ? CLICK_THROUGH_COPY.unavailableStatic
    : settings.scan_engine === "alfa"
      ? CLICK_THROUGH_COPY.unavailableAlfa
      : null;

  return (
    <SettingsGroup variant="plain" id="checks" legend={GROUPS.checks.legend} description={GROUPS.checks.description}>
      <div className="grid gap-5 sm:grid-cols-2">
        <PillGroup
          name="axe-level"
          label={STANDARD.label}
          hint={STANDARD.hint(settings.wcag_version)}
          value={settings.axe_level}
          onChange={(axe_level) => update({ axe_level })}
          options={[
            { value: "A", label: "Level A" },
            { value: "AA", label: "Level AA" },
            { value: "AAA", label: "Level AAA" },
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
          hint={rendered ? SWITCHES.keyboard.hint : "Needs a browser. Turn off Fast scan to use it."}
        />
        {!isFixed(policy, "skip_focus") && (
          <SwitchRow
            checked={switchOn(settings, "focus")}
            onChange={(on) => update(switchPatch(settings, "focus", on))}
            disabled={!rendered}
            label={SWITCHES.focus.label}
            hint={rendered ? SWITCHES.focus.hint : "Needs a browser. Turn off Fast scan to use it."}
          />
        )}
        {/* The page code check, after focus: like the switches above it, one
            switch per check that needs a browser, worded as what it checks
            (repo plain-language rules: a verb and an object). Its hint says
            it only reads the page, because the switches around it change
            or press the page and a reader deciding whether to turn one off
            needs to know which do (W3C COGA "Making Content Usable",
            https://www.w3.org/TR/coga-usable/, paraphrased: say what will
            happen). Hidden in a sign-in scan, which always runs it (fixed
            in the login policy), like the focus switch. */}
        {!isFixed(policy, "skip_markup") && (
          <SwitchRow
            checked={switchOn(settings, "markup")}
            onChange={(on) => update(switchPatch(settings, "markup", on))}
            disabled={!rendered}
            label={SWITCHES.markup.label}
            hint={rendered ? SWITCHES.markup.hint : "Needs a browser. Turn off Fast scan to use it."}
          />
        )}
        {/* One question with three answers, in place of the old on/off
            switch: don't check forms, check them without sending anything
            (the default for public websites), or check them and send empty
            ones to the site. The developer asked for the sending choice to
            replace the switch (2026-11-04). Rejected: the sending switch
            alone, which either sends by default on every public site or
            loses the safe check by default; and a second switch under this
            one, enabled only when it is on, which splits one decision
            across two controls whose meanings depend on each other (W3C
            COGA "Making Content Usable": one way to do one thing,
            https://www.w3.org/TR/coga-usable/). Native radios in a
            fieldset whose legend names the question (SC 1.3.1 Info and
            Relationships, Level A, technique H71), each answer's risk in
            its own hint (SC 3.3.2 Labels or Instructions, Level A). Not
            offered for signed-in scans (fixed in the login policy), so it
            is hidden there like the focus switch. */}
        {!isFixed(policy, "skip_forms") && (
          <PillGroup
            name="form-check"
            layout="list"
            label={SWITCHES.forms.label}
            hint={rendered ? SWITCHES.forms.hint : FORMS_CHOICE.needsBrowser}
            value={settings.skip_forms ? "off" : settings.send_empty_forms ? "send" : "page"}
            onChange={(choice) =>
              update({ skip_forms: choice === "off", send_empty_forms: choice === "send" })
            }
            options={[
              { value: "off", label: FORMS_CHOICE.off.label },
              { value: "page", label: FORMS_CHOICE.page.label, hint: FORMS_CHOICE.page.hint, disabled: !rendered },
              { value: "send", label: FORMS_CHOICE.send.label, hint: FORMS_CHOICE.send.hint, disabled: !rendered },
            ]}
          />
        )}
        <SwitchRow
          checked={switchOn(settings, "responsive")}
          onChange={(on) => update(switchPatch(settings, "responsive", on))}
          disabled={!rendered}
          label={SWITCHES.responsive.label}
          hint={rendered ? SWITCHES.responsive.hint : "Needs a browser. Turn off Fast scan to use it."}
        />
      </SwitchList>
    </SettingsGroup>
  );
}
