import { useEffect, useState, type FormEvent, type ReactNode, type Ref } from "react";
import { Disclosure } from "../ui";
import ChecksGroup from "./ChecksGroup";
import { GROUPS } from "./copy";
import CoverageGroup from "./CoverageGroup";
import FormErrorAlert from "./FormErrorAlert";
import type { Capabilities } from "./groupProps";
import LimitsGroup from "./LimitsGroup";
import LocalAiGroup from "./LocalAiGroup";
import type { FieldError, FieldKey, ScanPolicy, ScanSettings } from "./scanPolicy";
import ScanSummaryCard from "./ScanSummaryCard";
import { SCAN_PANEL_ID, scanTabId } from "./ScanTypeTabs";
import SpeedGroup from "./SpeedGroup";
import SubmitBar from "./SubmitBar";
import UrlHero from "./UrlHero";
import type { ScopePreviewState } from "./useScopePreview";
import type { ScopePreview } from "../../api/types";

/**
 * The whole scan form, for either mode.
 *
 * One component renders both tabs so they cannot drift: the same URL card,
 * the same setting cards, the same rail. A `ScanPolicy` decides the words
 * and which controls exist; the route owns the state, the queries and the
 * mutation, and passes them in. `beforeGroups` and `afterGroups` are where
 * the login form drops its authorization checkbox and its image-storage
 * acknowledgement.
 *
 * Every group is an open card, so the first screen already shows what will
 * run and the rail beside it says it in words. Only "Speed and debugging"
 * is folded away; a failed submit that names Fast crawl opens it, so the
 * alert's link lands on a visible switch. Start, Cancel and Reset sit in
 * the rail, under the summary they act on.
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
  fieldIds: Partial<Record<FieldKey, string>> & {
    url: string;
    static_only: string;
    max_pages: string;
    max_depth: string;
  };
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  pending: boolean;
  onCancel: () => void;
  urlInputRef?: Ref<HTMLInputElement>;
  beforeGroups?: ReactNode;
  afterGroups?: ReactNode;
}) {
  const urlError = errors.find((error) => error.field === "url")?.message;
  const groupProps = { settings, update, policy, capabilities, errors, fieldIds };

  // Keyed on the errors array itself, not on whether it names Fast crawl:
  // a second failed submit after the reader folded the group must open it
  // again.
  const [speedOpen, setSpeedOpen] = useState(false);
  useEffect(() => {
    if (errors.some((error) => error.field === "static_only")) setSpeedOpen(true);
  }, [errors]);

  return (
    // The tab panel is a div around the form: `tabpanel` is not a role a
    // <form> may carry (axe aria-allowed-role), and the form keeps its own
    // landmark semantics for a screen reader's form-mode.
    <div id={SCAN_PANEL_ID} role="tabpanel" aria-labelledby={scanTabId(policy.mode)} className="animate-drop-in">
      <form
        onSubmit={onSubmit}
        noValidate
        aria-labelledby={scanTabId(policy.mode)}
        className="lg:grid lg:grid-cols-[minmax(0,1fr)_17.5rem] lg:items-start lg:gap-5 xl:grid-cols-[minmax(0,1fr)_20rem] xl:gap-6"
      >
        <div className="flex min-w-0 flex-col gap-4">
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

          <CoverageGroup {...groupProps} />
          <ChecksGroup {...groupProps} />
          <LocalAiGroup {...groupProps} />
          <LimitsGroup {...groupProps} />
          <Disclosure
            id="speed-group"
            title={GROUPS.speed.legend}
            open={speedOpen}
            onOpenChange={setSpeedOpen}
            className="rounded-md"
          >
            <SpeedGroup {...groupProps} />
          </Disclosure>

          {afterGroups}
        </div>

        {/* Sticky beside the cards on a wide screen. The cap leaves room
            for the page header above the rail's first position, so its
            pinned actions are in view on arrival, not only after a scroll. */}
        <ScanSummaryCard
          settings={settings}
          policy={policy}
          preview={preview}
          capabilities={capabilities}
          className="mt-5 lg:sticky lg:top-24 lg:mt-0 lg:max-h-[calc(100vh-14rem)] lg:overflow-y-auto"
        >
          <SubmitBar
            label={policy.submitLabel}
            pendingLabel={policy.submitPendingLabel}
            pending={pending}
            note={policy.submitNote}
            onCancel={onCancel}
            onReset={onReset}
          />
        </ScanSummaryCard>
      </form>
    </div>
  );
}
