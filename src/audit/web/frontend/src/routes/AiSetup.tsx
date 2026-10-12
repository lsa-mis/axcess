import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Pause, Play, Trash2 } from "lucide-react";
import { useNavigate } from "react-router";
import { ApiError, api } from "../api/client";
import type {
  AiInstallStatus,
  AiPlan,
  AiTierId,
  AiTierPlan,
} from "../api/types";
import { Button, Card, LinkButton, PageHeader } from "../components/ui";
import { AiRuntimeControls } from "../components/AiRuntimeControls";
import { cn } from "../lib/cn";
import {
  AI_INSTALL_STATE_LABEL,
  AI_INSTALL_STEP_LABEL,
  AI_TIER_LABEL,
  AI_FEATURE_STATE_LABEL,
} from "../lib/terms";

/**
 * Settings > AI features: set up local AI on the desktop app, with consent.
 *
 * Why it looks and works this way (keep these when you change it):
 *
 * - A page of its own, not a row on Settings. Settings rows apply the moment
 *   they are chosen and stay on this computer; this page downloads several
 *   gigabytes. A separate step with one clear "Download and set up" button
 *   keeps a large download from ever starting by accident. WCAG 2.2 SC 3.3.4
 *   Error Prevention (Legal, Financial, Data), Level AA, does not strictly
 *   cover downloads; we follow its idea (paraphrased: an action with large
 *   consequences can be checked before it is done).
 * - What leaves the computer is said first and in plain words, before the
 *   choice: the program and models come in; reports never go out. The repo's
 *   plain-language rules (docs/plain-language.md) ask that no privacy fact is
 *   dropped to save space.
 * - The size choice is a native fieldset, legend and radio group, not cards
 *   with ARIA. Arrow keys move between sizes and a screen reader hears the
 *   question first. W3C "Using ARIA", rule 1
 *   (https://www.w3.org/TR/using-aria/#rule1, paraphrased: use the native
 *   element when it has the behaviour you need); WCAG technique H71.
 * - A size that may not fit is still choosable but says why in text, not
 *   by colour or by disabling it: the hardware check can be wrong, and a
 *   disabled option cannot be focused or explained. WCAG 2.2 SC 1.4.1 Use of
 *   Color, Level A.
 * - Progress is a native <progress> with a visible text value, and changes of
 *   step or state (not every byte) are said in a polite live region. WCAG 2.2
 *   SC 4.1.3 Status Messages, Level AA. Announcing every percent would talk
 *   over everything else the person does.
 * - Pause and Remove are separate buttons with their own words. Remove asks
 *   once more, inline, because it deletes the download. The confirmation is a
 *   second button that takes focus, not a modal: there is nothing else to
 *   decide. W3C COGA, "Making Content Usable" (https://www.w3.org/TR/coga-usable/):
 *   help people avoid mistakes, and say what will happen.
 * - Off and Remove are different actions: off keeps files, Remove deletes
 *   them. A native button says the next action and a heading says the current
 *   state, rather than an ambiguous toggle icon. Focus stays on the button
 *   after a change; a status region announces the result (WCAG 2.2 SC 2.4.3
 *   Focus Order, Level A, and SC 4.1.3 Status Messages, Level AA).
 *   While saving, aria-disabled plus an activation guard keeps that focused
 *   button in place; native disabled would blur it before the result arrives.
 */
export default function AiSetupRoute() {
  const queryClient = useQueryClient();
  const plan = useQuery({
    queryKey: ["ai-plan"],
    queryFn: api.getAiPlan,
    retry: false,
  });
  const running = plan.data?.install.state === "running";
  const install = useQuery({
    queryKey: ["ai-install"],
    queryFn: api.getAiInstall,
    enabled: running,
    refetchInterval: running ? 1000 : false,
  });
  const status: AiInstallStatus | undefined =
    install.data ?? plan.data?.install;

  // When the job leaves "running", reload the plan so the page shows the
  // finished setup, the pause, or the error.
  const lastState = useRef(status?.state);
  useEffect(() => {
    if (
      lastState.current === "running" &&
      status &&
      status.state !== "running"
    ) {
      void queryClient.invalidateQueries({ queryKey: ["ai-plan"] });
      void queryClient.invalidateQueries({ queryKey: ["suggestion-status"] });
      void queryClient.invalidateQueries({ queryKey: ["ai-preferences"] });
      void queryClient.invalidateQueries({ queryKey: ["capabilities", "local-analysis"] });
    }
    lastState.current = status?.state;
  }, [queryClient, status]);

  if (plan.isLoading) {
    return <p role="status">Loading AI settings…</p>;
  }
  if (plan.isError || !plan.data) {
    const notHere = plan.error instanceof ApiError && plan.error.status === 404;
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title="AI features" />
        <Card className="px-4 py-4 text-sm text-fg">
          {notHere
            ? "This page is part of the Axcess desktop app. On a shared server, the administrator sets up AI features. See docs/ai-suggestions.md."
            : "AI settings could not be loaded. Refresh the page to try again."}
        </Card>
      </div>
    );
  }
  return <AiSetupPage plan={plan.data} status={status ?? plan.data.install} />;
}

function AiSetupPage({
  plan,
  status,
}: {
  plan: AiPlan;
  status: AiInstallStatus;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const headingId = useId();
  const [chosen, setChosen] = useState<AiTierId | null>(
    status.tier ??
      plan.current?.tier ??
      plan.recommended ??
      plan.tiers[0]?.id ??
      null,
  );
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [message, setMessage] = useState("");
  const confirmRef = useRef<HTMLButtonElement>(null);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["ai-plan"] });
    void queryClient.invalidateQueries({ queryKey: ["ai-install"] });
    void queryClient.invalidateQueries({ queryKey: ["suggestion-status"] });
    void queryClient.invalidateQueries({ queryKey: ["ai-preferences"] });
    void queryClient.invalidateQueries({ queryKey: ["capabilities", "local-analysis"] });
  };
  const enabled = plan.preferences.enabled;
  const changeEnabled = useMutation({
    mutationFn: api.setAiEnabled,
    onMutate: () => setMessage("Saving AI settings…"),
    onSuccess: (preferences) => {
      queryClient.setQueryData(["ai-preferences"], preferences);
      setMessage(preferences.enabled
        ? "AI features are on. Scan checks still need your choice for each scan."
        : "AI features are off. Downloaded models and saved results are kept.");
      refresh();
    },
    onError: (error) => setMessage(
      error instanceof Error ? error.message : "AI settings could not be changed.",
    ),
  });
  const continueWithout = useMutation({
    mutationFn: () => api.setAiEnabled(false),
    onSuccess: (preferences) => {
      queryClient.setQueryData(["ai-preferences"], preferences);
      refresh();
      navigate("/scans");
    },
    onError: (error) => setMessage(
      error instanceof Error ? error.message : "Your choice could not be saved.",
    ),
  });
  const start = useMutation({
    mutationFn: (tier: AiTierId) => api.installAi(tier),
    onSuccess: (next) => {
      queryClient.setQueryData(["ai-install"], next);
      setMessage("Download started.");
      refresh();
    },
    onError: (error) =>
      setMessage(
        error instanceof Error
          ? error.message
          : "The download could not start.",
      ),
  });
  const pause = useMutation({
    mutationFn: api.pauseAiInstall,
    onSuccess: () => {
      setMessage("Download paused. What is already downloaded is kept.");
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: api.removeAi,
    onSuccess: () => {
      setConfirmRemove(false);
      setMessage("AI features removed.");
      refresh();
      // The Remove button is gone now, so focus moves to the size choice,
      // the next thing to act on, instead of falling back to the page top
      // (WCAG 2.2 SC 2.4.3 Focus Order, Level A).
      requestAnimationFrame(() =>
        document.querySelector<HTMLInputElement>(`input[name="${headingId}-tier"]:checked`)?.focus(),
      );
    },
    onError: () => setMessage("AI features could not be removed. Try again."),
  });

  useEffect(() => {
    if (confirmRemove) confirmRef.current?.focus();
  }, [confirmRemove]);

  // Announce a change of step or state, never each byte.
  const announced = useRef("");
  useEffect(() => {
    const text =
      status.state === "running" && status.step
        ? `${AI_INSTALL_STEP_LABEL[status.step]}.`
        : status.state === "done"
          ? "AI features are ready."
          : status.state === "failed"
            ? `AI setup stopped: ${status.error ?? "unknown problem"}`
            : "";
    if (text && text !== announced.current) {
      announced.current = text;
      setMessage(text);
    }
  }, [status.state, status.step, status.error]);

  const running = status.state === "running";
  const current = plan.current;
  const chosenTier = plan.tiers.find((t) => t.id === chosen);
  const hasDownload =
    status.state === "paused" || status.state === "failed" || running;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="AI features"
        subtitle="Optional. The AI runs on this computer."
      />
      <p
        role="status"
        className={cn(
          "text-sm font-semibold text-fg",
          message ? "mb-4" : "sr-only",
        )}
      >
        {message}
      </p>

      <div className="space-y-5">
        <Card className="space-y-2 border-l-4 border-l-umich-blue px-4 py-4 text-sm leading-6 text-fg">
          <h2 className="font-semibold">What AI features do</h2>
          <p>
            They suggest fixes for issues and can check images and wording
            during a scan. A person still checks every result: the AI can be
            wrong, and a scan never proves a site meets WCAG.
          </p>
          <h2 className="pt-2 font-semibold">
            What is downloaded, and what stays here
          </h2>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              {`Axcess downloads its own Ollama program, version ${plan.program.version} (${plan.program.licence} licence), from GitHub. It checks the published checksum before using it.`}
            </li>
            <li>Two AI models from the Ollama model library. Axcess checks each file before the isolated service reads it offline.</li>
            <li>The AI service cannot connect to the internet. Downloads run separately, only after you choose them.</li>
            <li>
              Your reports, pages and screenshots are never sent anywhere. The
              AI reads them on this computer.
            </li>
          </ul>
        </Card>

          <Card className="px-4 py-4 text-sm leading-6 text-fg">
            <h2 className="font-semibold">{AI_FEATURE_STATE_LABEL[enabled ? "on" : "off"]}</h2>
            <p className="mt-2">
              {enabled
                ? "AI fix suggestions are on when the local models are ready. AI checks during a scan stay off until you choose them for that scan."
                : "No new AI suggestions or model checks run. Regular checks, reading text inside images (OCR), and saved results still work. Downloaded models are kept."}
            </p>
            {current && <>
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
              <dt className="text-fg-muted">Size</dt>
              <dd>{AI_TIER_LABEL[current.tier]}</dd>
              <dt className="text-fg-muted">Text model</dt>
              <dd className="break-all font-mono text-xs leading-6">
                {current.text_model}
              </dd>
              <dt className="text-fg-muted">Image model</dt>
              <dd className="break-all font-mono text-xs leading-6">
                {current.vision_model}
              </dd>
              <dt className="text-fg-muted">Runs in</dt>
              <dd>
                {current.source === "system"
                  ? "Your own Ollama on this computer"
                  : "A private copy of Ollama that Axcess starts and stops"}
              </dd>
            </dl>
            </>}
            <AiRuntimeControls setupPage />
            {(enabled || current) && <Button
              className="mt-3"
              type="button"
              onClick={() => {
                if (!changeEnabled.isPending) changeEnabled.mutate(!enabled);
              }}
              disabled={running}
              aria-disabled={changeEnabled.isPending || undefined}
            >
              {enabled ? "Turn AI off" : "Turn AI on"}
            </Button>}
            {!enabled && current && <p className="mt-2 text-fg-muted">
              Turning AI on reuses these models. It does not download them again.
            </p>}
            {enabled && <p className="mt-2 text-fg-muted">
              Turning AI off stops Axcess’s private Ollama, not an Ollama you started yourself.
              Finish or stop current work before changing this setting.
            </p>}
          </Card>

        <Card className="px-4 py-4">
          <fieldset aria-describedby={`${headingId}-hw`} disabled={running}>
            <legend className="text-sm font-semibold text-fg">
              {current
                ? "Change the size of the AI models"
                : "Choose the size of the AI models"}
            </legend>
            <p
              id={`${headingId}-hw`}
              className="mt-1 text-xs leading-5 text-fg-muted"
            >
              {hardwareSentence(plan)} Bigger models give better answers but
              need more memory and are slower to download.
            </p>
            <div className="mt-3 space-y-2">
              {plan.tiers.map((tier) => (
                <TierOption
                  key={tier.id}
                  tier={tier}
                  name={`${headingId}-tier`}
                  recommended={tier.id === plan.recommended}
                  current={tier.id === current?.tier}
                  checked={tier.id === chosen}
                  memoryBytes={plan.hardware.memory_bytes}
                  onChoose={() => setChosen(tier.id)}
                />
              ))}
            </div>
            {plan.recommended === null && (
              <p className="mt-3 text-xs leading-5 text-fg">
                This computer has less memory or free disk space than even the
                small size needs. You can still try it, but it may be very slow
                or fail.
              </p>
            )}
          </fieldset>

          {running && (
            <div className="mt-4">
              <ProgressBlock status={status} />
            </div>
          )}
          {status.state === "failed" && status.error && (
            <p className="mt-4 text-sm text-fg">
              <span className="font-semibold">
                {AI_INSTALL_STATE_LABEL.failed}:{" "}
              </span>
              {status.error}
            </p>
          )}
          {status.state === "paused" && (
            <p className="mt-4 text-sm text-fg">
              {AI_INSTALL_STATE_LABEL.paused}. What is already downloaded is
              kept; resume to carry on.
            </p>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {running ? (
              <Button
                type="button"
                onClick={() => pause.mutate()}
                disabled={pause.isPending}
              >
                <Pause className="h-4 w-4" aria-hidden />
                Pause download
              </Button>
            ) : (
              // Keep the same-size download available to replace missing files
              // or move from a system Ollama to a private copy. Hiding it based
              // on the saved size would leave no repair action. The size-labelled
              // button keeps download consent separate from start (W3C COGA,
              // https://www.w3.org/TR/coga-usable/, paraphrased: prevent mistakes).
              chosenTier && (
                <Button
                  type="button"
                  variant="primary"
                  onClick={() => start.mutate(chosenTier.id)}
                  disabled={
                    start.isPending || !plan.program.available_for_this_computer
                  }
                >
                  {status.state === "paused" &&
                  status.tier === chosenTier.id ? (
                    <Play className="h-4 w-4" aria-hidden />
                  ) : (
                    <Download className="h-4 w-4" aria-hidden />
                  )}
                  {status.state === "paused" && status.tier === chosenTier.id
                    ? "Resume download"
                    : status.state === "failed" && status.tier === chosenTier.id
                      ? "Try again"
                      : `Download and set up (${formatBytes(chosenTier.download_bytes)})`}
                </Button>
              )
            )}
            {(current || hasDownload) && !running && !confirmRemove && (
              <Button type="button" onClick={() => setConfirmRemove(true)}>
                <Trash2 className="h-4 w-4" aria-hidden />
                Remove AI features
              </Button>
            )}
          </div>
          {!enabled && !current && <div className="mt-3">
            <p className="mb-2 text-sm text-fg">
              Download and set up turns AI on when setup finishes.
            </p>
            <Button type="button" onClick={() => {
              if (!continueWithout.isPending) continueWithout.mutate();
            }}
              disabled={running} aria-disabled={continueWithout.isPending || undefined}>
              Continue without AI
            </Button>
          </div>}
          {!plan.program.available_for_this_computer &&
            !plan.program.system_version && (
              <p className="mt-3 text-sm text-fg">
                Axcess has no private AI program for this kind of computer.
                AI stays off. Saved results still work.
              </p>
            )}

          {confirmRemove && (
            <div className="mt-4 rounded-xs border border-border-strong bg-surface-muted px-3 py-3 text-sm text-fg">
              <p>
                {current?.source === "system"
                  ? "This turns AI features off in Axcess. The models stay in your own Ollama, where other apps may use them."
                  : "This turns AI features off and deletes the Ollama program and models Axcess downloaded."}{" "}
                Reports are not changed.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  ref={confirmRef}
                  type="button"
                  variant="danger"
                  onClick={() => remove.mutate()}
                  disabled={remove.isPending}
                >
                  Yes, remove AI features
                </Button>
                <Button type="button" onClick={() => setConfirmRemove(false)}>
                  Keep them
                </Button>
              </div>
            </div>
          )}
        </Card>

        <p className="text-sm text-fg-muted">
          <LinkButton to="/settings" variant="ghost">
            Back to Settings
          </LinkButton>
        </p>
      </div>
    </div>
  );
}

function TierOption({
  tier,
  name,
  recommended,
  current,
  checked,
  memoryBytes,
  onChoose,
}: {
  tier: AiTierPlan;
  name: string;
  recommended: boolean;
  current: boolean;
  checked: boolean;
  memoryBytes: number;
  onChoose: () => void;
}) {
  const id = useId();
  const tooSmall = memoryBytes < tier.min_memory_gb * 1e9 * 0.95;
  const note = current
    ? " (in use now)"
    : recommended
      ? " (suggested for this computer)"
      : "";
  return (
    <label
      htmlFor={id}
      className={cn(
        "grid min-h-target cursor-pointer grid-cols-[auto_minmax(0,1fr)] gap-x-3 rounded-xs border px-3 py-2.5",
        // Chosen gets a thicker border and a tinted card, not only a colour.
        checked
          ? "border-2 border-umich-blue bg-surface-muted"
          : "border-border",
        "has-[:focus-visible]:outline has-[:focus-visible]:outline-[3px] has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-umich-blue",
      )}
    >
      <input
        id={id}
        type="radio"
        name={name}
        value={tier.id}
        checked={checked}
        onChange={onChoose}
        aria-describedby={`${id}-desc`}
        className="row-span-2 mt-1 h-4 w-4 shrink-0 accent-umich-blue"
      />
      <span className="text-sm font-semibold text-fg">
        {AI_TIER_LABEL[tier.id]}
        {note}
      </span>
      <span id={`${id}-desc`} className="text-xs leading-5 text-fg-muted">
        Needs {tier.min_memory_gb} GB of memory. Download:{" "}
        {formatBytes(tier.download_bytes)}.
        {tooSmall &&
          " This computer has less memory than this size needs, so it may be slow or fail."}
        {!tooSmall &&
          !tier.fits &&
          " There may not be enough free disk space for this size."}
        <span className="mt-0.5 block break-all">
          Text model: <span className="font-mono">{tier.text.tag}</span> (
          {licenceName(tier.text.licence)})
        </span>
        <span className="block break-all">
          Image model: <span className="font-mono">{tier.vision.tag}</span> (
          {licenceName(tier.vision.licence)})
        </span>
      </span>
    </label>
  );
}

function ProgressBlock({ status }: { status: AiInstallStatus }) {
  const id = useId();
  const percent =
    status.total_bytes > 0
      ? Math.floor((status.done_bytes / status.total_bytes) * 100)
      : 0;
  return (
    <div>
      <p id={id} className="text-sm font-semibold text-fg">
        {status.step
          ? AI_INSTALL_STEP_LABEL[status.step]
          : AI_INSTALL_STATE_LABEL.running}
      </p>
      <progress
        aria-labelledby={id}
        max={100}
        value={percent}
        className="mt-2 h-3 w-full accent-umich-blue"
      />
      <p className="mt-1 text-xs text-fg-muted">
        {percent}% · {formatBytes(status.done_bytes)} of about{" "}
        {formatBytes(status.total_bytes)}. You can keep using Axcess while it
        downloads.
      </p>
    </div>
  );
}

function hardwareSentence(plan: AiPlan): string {
  const memory = Math.round(plan.hardware.memory_bytes / 1024 ** 3);
  const disk = formatBytes(plan.hardware.free_disk_bytes);
  const chip = {
    apple: "an Apple chip",
    nvidia: "an NVIDIA graphics card",
    amd: "an AMD graphics card",
    none: "no graphics card Axcess can use, so AI answers will be slower",
  }[plan.hardware.accelerator];
  return `This computer has ${memory} GB of memory, ${disk} of free disk space, and ${chip}.`;
}

function licenceName(spdx: string): string {
  return spdx === "Apache-2.0" ? "Apache 2.0 licence" : `${spdx} licence`;
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${Math.round(bytes / 1e6)} MB`;
  return `${Math.max(0, Math.round(bytes / 1e3))} KB`;
}
