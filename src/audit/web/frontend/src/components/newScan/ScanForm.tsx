import type { FormEvent, ReactNode, Ref } from "react";
import { Disclosure } from "../ui";
import ChecksGroup, { checksCount } from "./ChecksGroup";
import CoverageGroup, { coverageCount } from "./CoverageGroup";
import DefaultSettingsCard from "./DefaultSettingsCard";
import FormErrorAlert from "./FormErrorAlert";
import type { Capabilities } from "./groupProps";
import LocalAiGroup, { localAiCount } from "./LocalAiGroup";
import type { FieldError, FieldKey, ScanPolicy, ScanSettings } from "./scanPolicy";
import ScanSummaryCard from "./ScanSummaryCard";
import { SCAN_PANEL_ID, scanTabId } from "./ScanTypeTabs";
import SpeedGroup from "./SpeedGroup";
import SubmitBar from "./SubmitBar";
import UrlHero from "./UrlHero";
import type { ScopePreviewState } from "./useScopePreview";
import type { ScopePreview } from "../../api/types";

function countMeta(count: { on: number; total: number }) {
  return (
    <span>
      {count.on} of {count.total} on
    </span>
  );
}

/**
 * The whole scan form, for either mode.
 *
 * One component renders both tabs so they cannot drift: the same hero, the
 * same default card, the same four groups, the same rail. A `ScanPolicy`
 * decides the words and which controls exist; the route owns the state, the
 * queries and the mutation, and passes them in. `beforeGroups` and
 * `afterGroups` are where the login form drops its authorization checkbox
 * and its image-storage acknowledgement.
 *
 * It is the tab panel, and it is keyed on the mode by the route, so a tab
 * change re-mounts it and it drops in (`animate-drop-in`, 300 ms, off under
 * reduced motion).
 */
export default function ScanForm({
  policy,
  settings,
  update,
  onReset,
  preview,
  capabilities,
  errors,
  fieldIds,
  onSubmit,
  pending,
  onCancel,
  urlInputRef,
  beforeGroups,
  afterGroups,
}: {
  policy: ScanPolicy;
  settings: ScanSettings;
  update: (patch: Partial<ScanSettings>) => void;
  onReset: () => void;
  preview: { state: ScopePreviewState; data: ScopePreview | null };
  capabilities: Capabilities;
  errors: FieldError[];
  fieldIds: Partial<Record<FieldKey, string>> & { url: string; static_only: string };
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  pending: boolean;
  onCancel: () => void;
  urlInputRef?: Ref<HTMLInputElement>;
  beforeGroups?: ReactNode;
  afterGroups?: ReactNode;
}) {
  const urlError = errors.find((error) => error.field === "url")?.message;
  const groupProps = { settings, update, policy, capabilities, errors, fieldIds };

  return (
    // The tab panel is a div around the form: `tabpanel` is not a role a
    // <form> may carry (axe aria-allowed-role), and the form keeps its own
    // landmark semantics for a screen reader's form-mode.
    <div
      id={SCAN_PANEL_ID}
      role="tabpanel"
      aria-labelledby={scanTabId(policy.mode)}
      // One framed panel for the form and the summary rail together, hung
      // from the tab rail above: the rail is part of what the tab switches,
      // not a sidebar that happens to sit beside it.
      className="animate-drop-in rounded-md border border-border bg-surface/60 p-4 sm:p-5"
    >
    <form
      onSubmit={onSubmit}
      noValidate
      aria-labelledby={scanTabId(policy.mode)}
      className="lg:grid lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start lg:gap-6"
    >
      <div className="flex min-w-0 flex-col gap-5">
        <FormErrorAlert errors={errors} fieldIds={fieldIds} />

        <UrlHero
          id={fieldIds.url}
          label={policy.urlLabel}
          help={policy.urlHelp}
          placeholder={policy.urlPlaceholder}
          value={settings.url}
          onChange={(url) => update({ url })}
          preview={preview}
          error={urlError}
          afterSignIn={policy.mode === "login"}
          autoFocus
          inputRef={urlInputRef}
        />

        {beforeGroups}

        <DefaultSettingsCard settings={settings} policy={policy} onReset={onReset} />

        <section aria-labelledby="advanced-settings-title" className="flex flex-col gap-2">
          <h2 id="advanced-settings-title" className="text-base font-semibold text-fg">
            Advanced settings
            <span className="ml-2 text-sm font-normal text-fg-muted">
              — change anything here and the card above shows what moved
            </span>
          </h2>
          <Disclosure
            id="coverage-group"
            title="Coverage"
            defaultOpen
            meta={countMeta(coverageCount(settings, policy))}
          >
            <CoverageGroup {...groupProps} />
          </Disclosure>
          <Disclosure
            id="checks-group"
            title="Checks"
            defaultOpen
            meta={countMeta(checksCount(settings, policy))}
          >
            <ChecksGroup {...groupProps} />
          </Disclosure>
          <Disclosure id="local-ai-group" title="Local AI" meta={countMeta(localAiCount(settings, policy))}>
            <LocalAiGroup {...groupProps} />
          </Disclosure>
          <Disclosure id="speed-group" title="Speed and debugging">
            <SpeedGroup {...groupProps} />
          </Disclosure>
        </section>

        {afterGroups}
      </div>

      <ScanSummaryCard
        settings={settings}
        policy={policy}
        preview={preview}
        capabilities={capabilities}
        className="mt-5 border-umich-blue/20 bg-umich-blue/[0.04] lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:mt-0 lg:sticky lg:top-24"
      />

      <SubmitBar
        label={policy.submitLabel}
        pendingLabel={policy.submitPendingLabel}
        pending={pending}
        note={policy.submitNote}
        onCancel={onCancel}
        className="mt-5 lg:col-start-1 lg:row-start-2"
      />
    </form>
    </div>
  );
}
