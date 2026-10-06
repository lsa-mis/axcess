import { useEffect, useState, type FormEvent, type ReactNode, type Ref } from "react";
import { withScheme } from "../../lib/webAddress";
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
import { SUBMIT_NOTE_ID } from "./SubmitBar";
import UrlHero from "./UrlHero";
import type { ScopePreviewState } from "./useScopePreview";
import type { ScopePreview } from "../../api/types";

/** The form's id, so Start in the page header (outside it) submits it. */
export const SCAN_FORM_ID = "scan-form";

type GroupKey = keyof typeof GROUPS;
const GROUP_KEYS: GroupKey[] = ["coverage", "checks", "localAi", "limits", "speed"];
/** The fields a failed submit can name, by the group that holds them. */
const GROUP_FIELDS: Record<GroupKey, readonly FieldKey[]> = {
  coverage: [],
  checks: [],
  localAi: [],
  limits: ["max_pages", "max_depth"],
  speed: ["static_only"],
};

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
 * Every settings group is an accordion row, closed on arrival: the first
 * screen is the address, the group names, and the rail beside them saying
 * in words what will run, so nothing has to be scrolled past to start. A
 * failed submit opens the group that holds a named field (the limits, or
 * Fast scan under Speed), so the alert's link lands on a visible control.
 * Start (`actions`) is pinned at the foot of the rail, and
 * Reset at its top right. Why the foot of the rail: see `SubmitBar`.
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
  urlInputRef,
  beforeGroups,
  afterGroups,
  actions,
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
  urlInputRef?: Ref<HTMLInputElement>;
  beforeGroups?: ReactNode;
  afterGroups?: ReactNode;
  /** Start (`SubmitBar`), pinned at the foot of the rail. */
  actions?: ReactNode;
}) {
  const urlError = errors.find((error) => error.field === "url")?.message;
  const groupProps = { settings, update, policy, capabilities, errors, fieldIds };

  // Which accordion rows are open; none on arrival. Keyed on the errors
  // array itself, not on which fields it names: a second failed submit after
  // the reader folded a group must open it again.
  const [open, setOpen] = useState<ReadonlySet<GroupKey>>(new Set());
  const setGroupOpen = (key: GroupKey) => (next: boolean) =>
    setOpen((current) => {
      const updated = new Set(current);
      if (next) updated.add(key);
      else updated.delete(key);
      return updated;
    });
  useEffect(() => {
    const named = GROUP_KEYS.filter((key) => errors.some((error) => GROUP_FIELDS[key].includes(error.field)));
    if (named.length) setOpen((current) => new Set([...current, ...named]));
  }, [errors]);
  const accordion = (key: GroupKey, children: ReactNode) => (
    <Disclosure
      id={`${key}-group`}
      title={GROUPS[key].legend}
      open={open.has(key)}
      onOpenChange={setGroupOpen(key)}
    >
      {children}
    </Disclosure>
  );

  return (
    // The tab panel is a div around the form: `tabpanel` is not a role a
    // <form> may carry (axe aria-allowed-role), and the form keeps its own
    // landmark semantics for a screen reader's form-mode.
    <div id={SCAN_PANEL_ID} role="tabpanel" aria-labelledby={scanTabId(policy.mode)} className="animate-drop-in">
      <form
        id={SCAN_FORM_ID}
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
            // On leaving the box, show the address as it will be scanned:
            // "example.edu" becomes "https://example.edu", "localhost:8000"
            // becomes "http://localhost:8000" (lib/webAddress.ts). Done on
            // blur, not while typing, so the text never changes under the
            // reader's cursor (SC 3.2.2 On Input, Level A).
            onBlur={() => {
              const completed = withScheme(settings.url);
              if (completed !== settings.url) update({ url: completed });
            }}
            preview={preview}
            error={urlError}
            afterSignIn={policy.mode === "login"}
            autoFocus
            inputRef={urlInputRef}
          />

          {beforeGroups}

          {accordion("coverage", <CoverageGroup {...groupProps} />)}
          {accordion("checks", <ChecksGroup {...groupProps} />)}
          {accordion("localAi", <LocalAiGroup {...groupProps} />)}
          {accordion("limits", <LimitsGroup {...groupProps} />)}
          {accordion("speed", <SpeedGroup {...groupProps} />)}

          {afterGroups}
        </div>

        {/* Sticky beside the groups on a wide screen, capped so the whole
            summary stays in view while a group is open. */}
        <ScanSummaryCard
          settings={settings}
          policy={policy}
          preview={preview}
          capabilities={capabilities}
          onReset={onReset}
          className="mt-5 lg:sticky lg:top-24 lg:mt-0"
        >
          {actions}
          {/* What happens after Start; this note is that button's
              description. */}
          {policy.submitNote && (
            <p id={SUBMIT_NOTE_ID} className="mt-3 text-xs text-fg-muted">
              {policy.submitNote}
            </p>
          )}
        </ScanSummaryCard>
      </form>
    </div>
  );
}
