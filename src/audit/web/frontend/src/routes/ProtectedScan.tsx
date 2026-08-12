import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { flushSync } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertOctagon, LockKeyhole, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router";
import { api } from "../api/client";
import {
  Button,
  Card,
  Checkbox,
  LinkButton,
  PageHeader,
} from "../components/ui";
import ProtectedScanSteps from "../components/ProtectedScanSteps";
import LocalLoginScan from "../components/LocalLoginScan";
import {
  protectedMutationKey,
  protectedQueryKey,
  useProtectedIdentityContext,
} from "../hooks/useProtectedIdentityContext";
import type {
  ProtectedDataClassification,
  ProtectedScanEngine,
  ProtectedScanEnvironment,
  ProtectedScanPayload,
} from "../api/types";
import EngineChoice from "./EngineChoice";

/**
 * Draft values are deliberately separate from the API payload: the three
 * origin lists are edited as readable newline-separated text and are only
 * converted to normalized exact origins at submit time.
 */
interface ProtectedScanForm {
  seed_url: string;
  target_owner: string;
  authorized_by: string;
  environment: ProtectedScanEnvironment;
  data_classification: ProtectedDataClassification;
  target_origins: string;
  auth_origins: string;
  resource_origins: string;
  authorization_acknowledged: boolean;
  least_privilege_account_acknowledged: boolean;
  scan_engine: ProtectedScanEngine;
  allow_local_ai: boolean;
  local_ai_acknowledged: boolean;
  max_pages: number;
  max_depth: number;
  rps: number;
}

const INITIAL_FORM: ProtectedScanForm = {
  seed_url: "",
  target_owner: "",
  authorized_by: "",
  environment: "staging",
  data_classification: "sensitive",
  target_origins: "",
  auth_origins: "",
  resource_origins: "",
  authorization_acknowledged: false,
  least_privilege_account_acknowledged: false,
  scan_engine: "both",
  allow_local_ai: false,
  local_ai_acknowledged: false,
  max_pages: 100,
  max_depth: 10,
  rps: 1,
};

/**
 * Validate an exact origin in the browser for immediate feedback. The server
 * remains authoritative: it additionally resolves every host and validates
 * redirects, IPs, browser requests, and resource URLs at crawl time.
 */
function exactOrigins(
  text: string,
  label: string,
  required: boolean,
): { origins: string[]; error: string | null } {
  const values = text
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);

  if (required && values.length === 0) {
    return { origins: [], error: `${label} needs at least one HTTPS origin.` };
  }

  const origins: string[] = [];
  for (const value of values) {
    if (value.includes("*")) {
      return {
        origins: [],
        error: `${label} cannot contain a wildcard. Enter one exact origin per line.`,
      };
    }

    let parsed: URL;
    try {
      parsed = new URL(value);
    } catch {
      return { origins: [], error: `${value} is not a valid ${label.toLowerCase()}.` };
    }

    if (
      parsed.protocol !== "https:" ||
      parsed.username ||
      parsed.password ||
      parsed.pathname !== "/" ||
      parsed.search ||
      parsed.hash
    ) {
      return {
        origins: [],
        error: `${value} must be an exact HTTPS origin with no path, query, fragment, or credentials.`,
      };
    }

    if (!origins.includes(parsed.origin)) origins.push(parsed.origin);
  }

  return { origins, error: null };
}

function protectedPayload(
  form: ProtectedScanForm,
): { payload: ProtectedScanPayload; error: null } | { payload: null; error: string } {
  let seed: URL;
  try {
    seed = new URL(form.seed_url.trim());
  } catch {
    return { payload: null, error: "Enter a valid HTTPS seed URL." };
  }

  if (
    seed.protocol !== "https:" ||
    seed.username ||
    seed.password ||
    seed.search ||
    seed.hash
  ) {
    return {
      payload: null,
      error:
        "The seed URL must use HTTPS and cannot include credentials, a query, or a fragment.",
    };
  }

  const target = exactOrigins(form.target_origins, "Target origins", true);
  if (target.error) return { payload: null, error: target.error };
  if (!target.origins.includes(seed.origin)) {
    return {
      payload: null,
      error: "Target origins must include the seed URL’s exact origin.",
    };
  }

  const auth = exactOrigins(form.auth_origins, "Authentication origins", false);
  if (auth.error) return { payload: null, error: auth.error };
  const resources = exactOrigins(form.resource_origins, "Resource origins", false);
  if (resources.error) return { payload: null, error: resources.error };

  if (!form.target_owner.trim() || !form.authorized_by.trim()) {
    return {
      payload: null,
      error: "Name the target owner and the person or group that authorized this scan.",
    };
  }
  if (!form.authorization_acknowledged) {
    return { payload: null, error: "Confirm that this protected evaluation is authorized." };
  }
  if (!form.least_privilege_account_acknowledged) {
    return {
      payload: null,
      error: "Confirm that you will use a dedicated least-privilege audit account.",
    };
  }
  if (form.allow_local_ai && !form.local_ai_acknowledged) {
    return {
      payload: null,
      error: "Acknowledge the local AI data-handling disclosure or leave local AI off.",
    };
  }
  if (
    !Number.isInteger(form.max_pages) ||
    form.max_pages < 1 ||
    form.max_pages > 10000 ||
    !Number.isInteger(form.max_depth) ||
    form.max_depth < 1 ||
    form.max_depth > 20 ||
    !Number.isFinite(form.rps) ||
    form.rps < 0.1 ||
    form.rps > 10
  ) {
    return { payload: null, error: "Check the protected crawl limits and rate." };
  }

  return {
    payload: {
      seed_url: seed.toString(),
      target_owner: form.target_owner.trim(),
      authorized_by: form.authorized_by.trim(),
      environment: form.environment,
      data_classification: form.data_classification,
      authorization_acknowledged: true,
      least_privilege_account_acknowledged: true,
      approved_target_origins: target.origins,
      ...(auth.origins.length > 0 ? { approved_auth_origins: auth.origins } : {}),
      ...(resources.origins.length > 0
        ? { approved_cdn_origins: resources.origins }
        : {}),
      scan_engine: form.scan_engine,
      allow_local_ai: form.allow_local_ai,
      local_ai_acknowledged: form.allow_local_ai
        ? form.local_ai_acknowledged
        : undefined,
      max_pages: form.max_pages,
      max_depth: form.max_depth,
      rps: form.rps,
    },
    error: null,
  };
}

/**
 * Create an authorized protected scan. This route collects scope and consent
 * metadata only; a companion on the auditor's own computer performs the
 * visible, manual sign-in after the server creates the scan draft.
 */
export default function ProtectedScanRoute() {
  const capability = useQuery({
    queryKey: ["capabilities", "protected-scans"],
    queryFn: api.getProtectedScanCapability,
    retry: false,
  });

  if (capability.isLoading) {
    return (
      <>
        <ProtectedScanHeader />
        <p className="text-sm text-fg-muted" aria-live="polite">
          Checking secure login-scan readiness…
        </p>
      </>
    );
  }
  if (capability.data?.local_available) {
    return (
      <>
        <ProtectedScanHeader />
        <LocalLoginScan />
      </>
    );
  }
  if (capability.error || capability.data?.available === false) {
    return (
      <>
        <ProtectedScanHeader />
        <ProtectedScanSteps current="scope" className="mb-5" />
        <Card className="max-w-3xl border-sev-major/40 bg-sev-major-bg p-5" role="note">
          <p className="text-xs font-semibold uppercase tracking-wide text-sev-major">Not ready on this server</p>
          <h2 className="mt-1 text-lg font-semibold text-fg">Connect the protected-scan services</h2>
          <p className="mt-2 text-sm text-fg-muted">
            {capability.error instanceof Error
              ? capability.error.message
              : capability.data?.reason ?? "Secure login scanning is unavailable on this server."}
          </p>
          <p className="mt-4 text-sm text-fg">
            An administrator must connect U-M identity verification, the companion certificate service, and managed report-key revocation. These controls prevent another browser or device from starting an authenticated crawl or reading its evidence.
          </p>
          <p className="mt-4 text-sm text-fg-muted">
            Axcess never asks for or stores your password, one-time code, push approval, passkey, recovery code, cookies, or reusable browser session.
          </p>
          <LinkButton to="/scans/new" variant="secondary" className="mt-4">
            Use a public scan
          </LinkButton>
        </Card>
      </>
    );
  }

  return <EnterpriseProtectedScanRoute />;
}

function EnterpriseProtectedScanRoute() {
  const protectedIdentity = useProtectedIdentityContext();

  if (protectedIdentity.isChecking) {
    return (
      <>
        <ProtectedScanHeader />
        <p className="text-sm text-fg-muted" aria-live="polite">
          Verifying protected-scan access…
        </p>
      </>
    );
  }
  if (
    protectedIdentity.error ||
    !protectedIdentity.isReady ||
    !protectedIdentity.fingerprint
  ) {
    return (
      <>
        <ProtectedScanHeader />
        <Card
          className="border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical"
          role="alert"
        >
          {protectedIdentity.error instanceof Error
            ? protectedIdentity.error.message
            : "Protected-scan access is unavailable."}
        </Card>
      </>
    );
  }

  // A proxy identity switch remounts the form so target origins and the
  // authorization draft from one expert cannot appear to the next user of a
  // shared browser tab.
  return (
    <ProtectedScanFormRoute
      key={protectedIdentity.fingerprint}
      identityFingerprint={protectedIdentity.fingerprint}
    />
  );
}

function ProtectedScanFormRoute({
  identityFingerprint,
}: {
  identityFingerprint: string;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isCurrentIdentity = useRef(true);
  const [form, setForm] = useState<ProtectedScanForm>(INITIAL_FORM);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const alfaCapability = useQuery({
    queryKey: ["capabilities", "alfa"],
    queryFn: api.getAlfaCapability,
  });

  useEffect(() => {
    if (alfaCapability.data?.available === false && form.scan_engine !== "axe") {
      setForm((previous) => ({ ...previous, scan_engine: "axe" }));
    }
  }, [alfaCapability.data?.available, form.scan_engine]);

  useEffect(() => {
    if (submitError) errorRef.current?.focus();
  }, [submitError]);

  useEffect(
    () => () => {
      isCurrentIdentity.current = false;
    },
    [],
  );

  const create = useMutation({
    mutationKey: protectedMutationKey("scan-create", identityFingerprint),
    mutationFn: (payload: ProtectedScanPayload) => api.createProtectedScan(payload),
    gcTime: 0,
    onSuccess: ({ scan_id }) => {
      if (!isCurrentIdentity.current) return;
      void queryClient.invalidateQueries({
        queryKey: protectedQueryKey("reports", identityFingerprint),
      });
      // A protected draft needs a companion handoff before it can scan, so
      // land directly on the next actionable step rather than the generic
      // report overview.
      navigate(`/scans/${scan_id}/protected`);
    },
    onError: (error: unknown) => {
      if (isCurrentIdentity.current) {
        setSubmitError(error instanceof Error ? error.message : String(error));
      }
    },
  });

  useEffect(() => {
    const clearDraft = () => {
      // Exact origins, the seed path, and approval references are protected
      // scope data. They are never persisted by this form, but a browser can
      // preserve React's in-memory DOM snapshot in its back/forward cache.
      // Clear the draft synchronously before that snapshot is taken so a
      // later proxy-user switch cannot reveal an unfinished evaluation.
      flushSync(() => {
        setForm(INITIAL_FORM);
        setSubmitError(null);
      });
      create.reset();
    };
    const onPageHide = () => clearDraft();
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) clearDraft();
    };

    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("pageshow", onPageShow);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      window.removeEventListener("pageshow", onPageShow);
    };
  }, [create]);

  const update = <K extends keyof ProtectedScanForm>(
    key: K,
    value: ProtectedScanForm[K],
  ) => setForm((previous) => ({ ...previous, [key]: value }));

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);
    const result = protectedPayload(form);
    if (result.payload === null) {
      setSubmitError(result.error);
      return;
    }
    create.mutate(result.payload);
  };

  const alfaUnavailable = alfaCapability.data?.available === false;

  return (
    <>
      <ProtectedScanHeader />
      <ProtectedScanSteps current="scope" className="mb-5" />

      <Card className="mb-4 border-umich-blue/30 bg-umich-blue/5 p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
          <div>
            <h2 className="text-sm font-semibold text-fg">You control the sign-in</h2>
            <p className="mt-1 text-sm text-fg-muted">
              After you save this draft, the paired Axcess companion opens a headed browser on your computer. Complete 1FA or MFA directly with the site. Passwords, one-time codes, passkeys, recovery codes, cookies, and browser session state never belong in this form.
            </p>
          </div>
        </div>
      </Card>

      {submitError && (
        <Card
          className="mb-4 border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical"
        >
          <div
            ref={errorRef}
            tabIndex={-1}
            role="alert"
            className="flex items-start gap-3 focus:outline-none"
          >
            <AlertOctagon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
            <div>{submitError}</div>
          </div>
        </Card>
      )}

      <Card className="max-w-4xl p-5">
        <form onSubmit={submit} className="flex flex-col gap-6">
          <fieldset className="rounded-xs border border-border p-4">
            <legend className="px-1 text-sm font-semibold text-fg">Authorization and accountability</legend>
            <p className="mb-4 text-sm text-fg-muted">
              Protected crawling is for an explicitly authorized accessibility evaluation. Do not use it for a penetration test, account discovery, or bypassing an access control.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField
                id="protected-target-owner"
                label="Target owner"
                value={form.target_owner}
                required
                hint="The person, team, or service owner responsible for the target."
                onChange={(value) => update("target_owner", value)}
              />
              <TextField
                id="protected-authorized-by"
                label="Authorization reference"
                value={form.authorized_by}
                required
                hint="The approving person, group, or ticket reference. Axcess records the verified proxy identity as the requester."
                onChange={(value) => update("authorized_by", value)}
              />
              <SelectField
                id="protected-environment"
                label="Environment"
                value={form.environment}
                onChange={(value) =>
                  update("environment", value as ProtectedScanEnvironment)
                }
              >
                <option value="staging">Authorized staging or test</option>
                <option value="production">Authorized production</option>
              </SelectField>
              <SelectField
                id="protected-data-classification"
                label="Data classification"
                value={form.data_classification}
                onChange={(value) =>
                  update(
                    "data_classification",
                    value as ProtectedDataClassification,
                  )
                }
              >
                <option value="internal">Internal</option>
                <option value="sensitive">Sensitive</option>
                <option value="restricted">Restricted</option>
              </SelectField>
            </div>
            <div className="mt-4 space-y-1">
              <Checkbox
                id="protected-authorization"
                checked={form.authorization_acknowledged}
                onChange={(value) => update("authorization_acknowledged", value)}
                label="I confirm that this scope, environment, and evaluation are explicitly authorized."
                hint="Axcess records this acknowledgement with the report; it does not replace the owner’s approval process."
              />
              <Checkbox
                id="protected-least-privilege"
                checked={form.least_privilege_account_acknowledged}
                onChange={(value) =>
                  update("least_privilege_account_acknowledged", value)
                }
                label="I will use a dedicated least-privilege audit account, never an administrator or personal account."
                hint="The companion stops rather than trying to re-authenticate if the session expires or requires a new factor."
              />
            </div>
          </fieldset>

          <fieldset className="rounded-xs border border-border p-4">
            <legend className="px-1 text-sm font-semibold text-fg">Approved scope</legend>
            <p className="mb-4 text-sm text-fg-muted">
              Enter one exact HTTPS origin on each line. Paths, wildcard domains, user names, passwords, query strings, and fragments are rejected. The service rechecks redirects and resolved IP addresses while crawling. Exact origins are encrypted into the scan-bound companion work item; the report later shows only counts and opaque scope tags.
            </p>
            <div className="space-y-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-base font-semibold text-fg">Protected seed URL</span>
                <input
                  id="protected-seed-url"
                  type="url"
                  required
                  autoFocus
                  placeholder="https://app.example.edu/dashboard"
                  value={form.seed_url}
                  onChange={(event) => update("seed_url", event.target.value)}
                  aria-describedby="protected-seed-url-hint"
                  className="min-h-target rounded-xs border-2 border-border bg-surface px-4 py-3 text-base text-fg focus:border-umich-blue focus:outline-none"
                />
                <span id="protected-seed-url-hint" className="text-xs text-fg-muted">
                  Use the post-auth application URL, not a sign-in, identity-provider, logout, password-reset, or one-time-link URL.
                </span>
              </label>
              <OriginListField
                id="protected-target-origins"
                label="Approved target origins"
                value={form.target_origins}
                required
                hint="Pages are crawled only from these origins. Include the seed URL’s origin."
                placeholder="https://app.example.edu"
                onChange={(value) => update("target_origins", value)}
              />
              <OriginListField
                id="protected-auth-origins"
                label="Approved authentication origins (optional)"
                value={form.auth_origins}
                hint="Only used while you manually sign in. Authentication pages are never saved as crawl evidence."
                placeholder="https://login.example.edu"
                onChange={(value) => update("auth_origins", value)}
              />
              <OriginListField
                id="protected-resource-origins"
                label="Approved resource / CDN origins (optional)"
                value={form.resource_origins}
                hint="Only list origins necessary to render approved pages, such as a first-party image CDN. They are not added to page crawl scope."
                placeholder="https://assets.example.edu"
                onChange={(value) => update("resource_origins", value)}
              />
            </div>
          </fieldset>

          <fieldset className="rounded-xs border border-border p-4">
            <legend className="px-1 text-sm font-semibold text-fg">Read-only methods and limits</legend>
            <p className="mb-3 text-sm text-fg-muted">
              Protected scans allow only approved GET and HEAD requests. Forms, downloads, pop-ups, workers, and state-changing network methods are blocked. A GET request can still have target-side effects, so keep the scope small and use the owner-approved account.
            </p>
            <fieldset className="rounded-xs border border-border p-3">
              <legend className="px-1 text-sm font-medium text-fg">Scan engine</legend>
              <p id="protected-engine-hint" className="mb-2 text-xs text-fg-muted">
                Alfa and axe-core run only inside the companion’s authenticated browser scope. Their results are evidence for expert review, not a conformance verdict.
              </p>
              <div className="space-y-2" role="radiogroup" aria-describedby="protected-engine-hint">
                <EngineChoice
                  value="axe"
                  selected={form.scan_engine}
                  onChange={(value) => update("scan_engine", value)}
                  label="axe-core"
                  hint="Fast DOM and computed-style checks in the authenticated browser."
                />
                <EngineChoice
                  value="both"
                  selected={form.scan_engine}
                  onChange={(value) => update("scan_engine", value)}
                  disabled={alfaUnavailable}
                  label="axe-core + Siteimprove Alfa"
                  hint="Recommended for independent engine coverage; slower because Alfa runs a separate local browser capture."
                />
                <EngineChoice
                  value="alfa"
                  selected={form.scan_engine}
                  onChange={(value) => update("scan_engine", value)}
                  disabled={alfaUnavailable}
                  label="Siteimprove Alfa only"
                  hint="ACT means Accessibility Conformance Testing. Each standardized rule checks one specific condition; Alfa also records when an expert must decide the outcome."
                />
              </div>
              {alfaUnavailable && (
                <p className="mt-2 text-xs text-sev-major" role="status">
                  Alfa is unavailable: {alfaCapability.data?.reason}
                </p>
              )}
            </fieldset>
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <NumberField
                id="protected-max-pages"
                label="Maximum pages"
                value={form.max_pages}
                min={1}
                max={10000}
                onChange={(value) => update("max_pages", value)}
              />
              <NumberField
                id="protected-max-depth"
                label="Maximum depth"
                value={form.max_depth}
                min={1}
                max={20}
                onChange={(value) => update("max_depth", value)}
              />
              <NumberField
                id="protected-rps"
                label="Requests / second"
                value={form.rps}
                min={0.1}
                max={50}
                step={0.1}
                onChange={(value) => update("rps", value)}
              />
            </div>
          </fieldset>

          <fieldset className="rounded-xs border border-border p-4">
            <legend className="px-1 text-sm font-semibold text-fg">Optional local AI</legend>
            <div className="flex items-start gap-3 rounded-xs border border-sev-major/40 bg-sev-major-bg/40 p-3">
              <LockKeyhole className="mt-0.5 h-5 w-5 shrink-0 text-sev-major" aria-hidden />
              <p className="text-sm text-fg">
                Local AI is off by default. If enabled, only a companion-verified Ollama endpoint at a literal loopback IP address may receive bounded, in-memory protected image bytes. It never receives page evidence. Axcess must not use a remote provider, MCP chat, or webhook for this scan.
              </p>
            </div>
            <div className="mt-3 space-y-1">
              <Checkbox
                id="protected-local-ai"
                checked={form.allow_local_ai}
                onChange={(value) => {
                  update("allow_local_ai", value);
                  if (!value) update("local_ai_acknowledged", false);
                }}
                label="Enable local AI analysis for this protected scan"
                hint="The companion independently verifies the endpoint; this checkbox cannot enable an external model."
                tone="warning"
              />
              {form.allow_local_ai && (
                <Checkbox
                  id="protected-local-ai-acknowledged"
                  checked={form.local_ai_acknowledged}
                  onChange={(value) => update("local_ai_acknowledged", value)}
                  label="I understand that bounded protected image bytes may be processed by the local Ollama service on this computer."
                  hint="Use a literal loopback address such as 127.0.0.1 or ::1, not localhost. Do not enable this if that local service is shared, remotely reachable, or not approved for the selected data classification."
                  tone="warning"
                />
              )}
            </div>
          </fieldset>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="submit"
              variant="primary"
              size="lg"
              disabled={
                create.isPending ||
                !form.seed_url.trim() ||
                !form.target_owner.trim() ||
                !form.authorized_by.trim() ||
                !form.authorization_acknowledged ||
                !form.least_privilege_account_acknowledged ||
                (form.allow_local_ai && !form.local_ai_acknowledged) ||
                alfaUnavailable && form.scan_engine !== "axe"
              }
            >
              {create.isPending ? "Creating protected draft…" : "Create protected scan draft"}
            </Button>
            <Button type="button" onClick={() => navigate("/scans")}>
              Cancel
            </Button>
            <span className="text-sm text-fg-muted" aria-live="polite">
              {create.isPending
                ? "Creating the draft. No browser sign-in or crawl has started yet."
                : "The companion will request manual sign-in after the draft is created."}
            </span>
          </div>
        </form>
      </Card>
    </>
  );
}

function ProtectedScanHeader() {
  return (
    <PageHeader
      crumbs={[
        { label: "Scans", to: "/scans" },
        { label: "2FA / login scan" },
      ]}
      title="2FA / login scan"
      subtitle="Sign in yourself in a visible local browser. After Axcess verifies the approved post-login page, it scans with that temporary session."
      actions={
        <LinkButton to="/scans/new" variant="secondary">
          Public scan instead
        </LinkButton>
      }
    />
  );
}

function TextField({
  id,
  label,
  value,
  onChange,
  hint,
  required = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint: string;
  required?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-fg">{label}</span>
      <input
        id={id}
        type="text"
        required={required}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={`${id}-hint`}
        className="min-h-target rounded-xs border border-border bg-surface px-3 py-2 text-base text-fg focus:border-umich-blue focus:outline-none"
      />
      <span id={`${id}-hint`} className="text-xs text-fg-muted">{hint}</span>
    </label>
  );
}

function SelectField({
  id,
  label,
  value,
  onChange,
  children,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-fg">{label}</span>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-target rounded-xs border border-border bg-surface px-3 py-2 text-base text-fg focus:border-umich-blue focus:outline-none"
      >
        {children}
      </select>
    </label>
  );
}

function OriginListField({
  id,
  label,
  value,
  onChange,
  hint,
  placeholder,
  required = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint: string;
  placeholder: string;
  required?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-fg">{label}</span>
      <textarea
        id={id}
        required={required}
        rows={3}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={`${id}-hint`}
        placeholder={placeholder}
        className="min-h-[96px] rounded-xs border border-border bg-surface px-3 py-2 font-mono text-sm text-fg focus:border-umich-blue focus:outline-none"
      />
      <span id={`${id}-hint`} className="text-xs text-fg-muted">{hint}</span>
    </label>
  );
}

function NumberField({
  id,
  label,
  value,
  onChange,
  min,
  max,
  step,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
      {label}
      <input
        id={id}
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
        className="min-h-target rounded-xs border border-border bg-surface px-3 py-2 text-base font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
      />
    </label>
  );
}

// Exported for lightweight unit tests without mounting React. It is not a
// security boundary — the server repeats and extends these checks.
export { exactOrigins, protectedPayload };
