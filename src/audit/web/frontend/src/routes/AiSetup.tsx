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
  MyModelFile,
} from "../api/types";
import { Button, Card, LinkButton, PageHeader } from "../components/ui";
import { AiRuntimeControls } from "../components/AiRuntimeControls";
import { cn } from "../lib/cn";
import {
  AI_INSTALL_STATE_LABEL,
  AI_INSTALL_STEP_LABEL,
  AI_TIER_LABEL,
  AI_FEATURE_STATE_LABEL,
  AI_MY_MODEL_LABEL,
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
      (plan.current?.tier === "custom" ? null : plan.current?.tier) ??
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
  // The chosen size is the private setup in use and every file is here, so
  // there is nothing to download (see the rationale at the button).
  const chosenIsSetUp =
    chosenTier !== undefined &&
    chosenTier.installed &&
    current?.source === "private" &&
    current.backend === "llama_cpp" &&
    current.tier === chosenTier.id;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="AI features"
        subtitle="Optional. The AI suggests fixes and checks images and wording, on this computer."
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
        {/* Facts first, short: one sentence on limits, three on privacy.
            Rejected: the earlier two headings and four long bullets, which
            repeated "on this computer" and buried the main point. Every
            limitation and privacy fact is kept, said more simply (repo
            plain-language rule; W3C COGA Making Content Usable,
            https://www.w3.org/TR/coga-usable/, paraphrased: one idea per
            chunk, short text). */}
        <Card className="space-y-2 border-l-4 border-l-umich-blue px-4 py-4 text-sm leading-6 text-fg">
          <p>
            The AI can be wrong, so a person checks every result. A scan never
            proves a site meets WCAG.
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              {plan.program.included
                ? `Downloads: the AI models for the size you choose, from Hugging Face, a website that shares AI models. The AI program (llama.cpp ${plan.program.version}, ${plan.program.licence} licence) comes with Axcess. Axcess checks every file first.`
                : `Downloads: the AI program (llama.cpp ${plan.program.version}, ${plan.program.licence} licence) from GitHub and the AI models for the size you choose, from Hugging Face, a website that shares AI models. Axcess checks every file first.`}
            </li>
            <li>The private AI service cannot reach the internet.</li>
            <li>Your reports, pages and screenshots are never sent anywhere.</li>
          </ul>
        </Card>

          <Card className="px-4 py-4 text-sm leading-6 text-fg">
            <h2 className="font-semibold">{AI_FEATURE_STATE_LABEL[enabled ? "on" : "off"]}</h2>
            <p className="mt-2">
              {enabled
                ? "You can ask for fix suggestions. AI checks during a scan stay off until you turn them on for that scan."
                : "No new AI suggestions or model checks run. Regular checks, reading text inside images (OCR), and saved results still work. Downloaded models are kept."}
            </p>
            {current && <p className="mt-2">
              {current.tier === "custom"
                ? `Model: ${AI_MY_MODEL_LABEL}${current.custom_model ? ` (${current.custom_model.tag})` : ""}.`
                : `Size: ${AI_TIER_LABEL[current.tier]}.`}
            </p>}
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
              Turning AI off keeps the models and stops only Axcess’s private AI service. Finish current work first.
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
              need more memory.
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

          {/* Model names and licences are for people who need them (an IT
              check, say), so they sit one press away instead of in every
              size option. Rejected: repeating two model lines inside each
              option, which made the choice hard to scan. Native details and
              summary give keyboard and screen-reader support for free (W3C
              "Using ARIA", rule 1, https://www.w3.org/TR/using-aria/#rule1,
              paraphrased); COGA, paraphrased: show the main choice first. */}
          <details className="mt-3 text-xs leading-5 text-fg">
            <summary className="min-h-target cursor-pointer content-center text-sm font-semibold">
              Model names and licences
            </summary>
            <ul className="space-y-1">
              {plan.tiers.map((tier) => (
                <li key={tier.id} className="break-all">
                  <span className="font-semibold">{AI_TIER_LABEL[tier.id]}:</span>{" "}
                  {tier.text.tag === tier.vision.tag ? (
                    // One model that reads text and images (Small).
                    <>
                      text and image <span className="font-mono">{tier.text.tag}</span> (
                      {licenceName(tier.text.licence)})
                    </>
                  ) : (
                    <>
                      text <span className="font-mono">{tier.text.tag}</span> (
                      {licenceName(tier.text.licence)}), image{" "}
                      <span className="font-mono">{tier.vision.tag}</span> (
                      {licenceName(tier.vision.licence)})
                    </>
                  )}
                </li>
              ))}
            </ul>
          </details>

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
            ) : chosenIsSetUp ? (
              // The chosen size is set up and every file is checked: a line
              // says so where the button was (2026-11-17, the developer's
              // request: after the download the page still offered "Download
              // and set up"). Rejected: a greyed-out (disabled) button, which
              // keyboard users cannot reach and whose reason a screen reader
              // does not hear; one line of text says the same to everyone
              // (W3C COGA Making Content Usable,
              // https://www.w3.org/TR/coga-usable/, paraphrased: do not offer
              // controls that cannot work). Choosing another size brings the
              // button back.
              <p className="min-h-target content-center text-sm font-semibold text-fg">
                {`${AI_TIER_LABEL[chosenTier.id]} is set up on this computer. Nothing to download.`}
              </p>
            ) : (
              // Otherwise keep the download available, the same size included:
              // to replace missing files, to move from a system Ollama to the
              // private service, or to replace a private Ollama setup saved
              // before llama.cpp (its models no longer run). Hiding it based
              // on the saved size alone would leave no repair action. The
              // size-labelled button keeps download consent separate from
              // start (W3C COGA, https://www.w3.org/TR/coga-usable/,
              // paraphrased: prevent mistakes).
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
          {!plan.program.available_for_this_computer && (
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
                  : "This turns AI features off and deletes the AI files Axcess downloaded."}{" "}
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

        <MyModelCard plan={plan} disabled={running} onMessage={setMessage} />

        <p className="text-sm text-fg-muted">
          <LinkButton to="/settings" variant="ghost">
            Back to Settings
          </LinkButton>
        </p>
      </div>
    </div>
  );
}

/**
 * "Use your own model": run a GGUF file the person chose instead of a size,
 * for trying models the catalogue does not offer (developer, 2026-11-17).
 *
 * - Native file inputs with visible labels, not a drop zone: they work by
 *   keyboard and screen reader everywhere, including the desktop app,
 *   which has no file dialog of its own. W3C "Using ARIA", rule 1
 *   (https://www.w3.org/TR/using-aria/#rule1, paraphrased: use the native
 *   element); WCAG technique H44 (label elements).
 * - Its own card below the sizes, not a fifth size: it has no download,
 *   no memory check and no pinned checksum, so it cannot promise what a
 *   size promises. The card says so in plain words before the choice
 *   (repo plain-language rule: never drop a limitation or safety fact).
 * - One button copies and starts the model. Copying alone would leave a
 *   second step with nothing to decide (W3C COGA Making Content Usable,
 *   https://www.w3.org/TR/coga-usable/, paraphrased: fewer steps). Models
 *   copied before are listed with a "Use ..." button each, named with the
 *   model, so switching between them for a comparison needs no new copy
 *   (WCAG 2.2 SC 2.4.6 Headings and Labels, Level AA: the button says
 *   which model).
 * - Copy progress is a native <progress> with a visible percent; only the
 *   change of step is announced, in the page's status region (SC 4.1.3
 *   Status Messages, Level AA), as the size download does.
 * - Answer settings (sampling) sit in a closed native <details> above the
 *   file choice, because most people never need them and the model's own
 *   page gives the values to copy (developer, 2026-11-17: "allow user to
 *   tune top k top p and other important parameters"). One set applies to
 *   whichever model this card starts next, the copy and the "Use ..."
 *   buttons alike, so there is one place to set them, not one per model
 *   (W3C COGA Making Content Usable, paraphrased: one way to do one
 *   thing). Each field is a native number input with a visible label that
 *   puts the plain phrase first and the technical name in parentheses
 *   (repo plain-language rule 3; WCAG technique H44), and its allowed range
 *   in words, not only in min/max (SC 3.3.2 Labels or Instructions,
 *   Level A). A value out of range is named in the status region and its
 *   field takes focus (SC 3.3.1 Error Identification, Level A).
 */
const SAMPLING_FIELDS: {
  key: "temp" | "top-p" | "top-k" | "min-p" | "presence-penalty" | "repeat-penalty";
  label: string;
  min: number;
  max: number;
  step: string;
}[] = [
  { key: "temp", label: "Randomness (temperature), 0 to 2", min: 0, max: 2, step: "any" },
  { key: "top-p", label: "Word choice by share (top-p), 0 to 1", min: 0, max: 1, step: "any" },
  { key: "top-k", label: "Word choice by count (top-k), 0 to 1000", min: 0, max: 1000, step: "1" },
  { key: "min-p", label: "Least likely word kept (min-p), 0 to 1", min: 0, max: 1, step: "any" },
  {
    key: "presence-penalty",
    label: "Penalty for any repeated word (presence penalty), -2 to 2",
    min: -2,
    max: 2,
    step: "any",
  },
  {
    key: "repeat-penalty",
    label: "Penalty for repeating often (repetition penalty), 0 to 2",
    min: 0,
    max: 2,
    step: "any",
  },
];

function MyModelCard({
  plan,
  disabled,
  onMessage,
}: {
  plan: AiPlan;
  disabled: boolean;
  onMessage: (text: string) => void;
}) {
  const queryClient = useQueryClient();
  const id = useId();
  const modelInput = useRef<HTMLInputElement>(null);
  const addonInput = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<{ label: string; fraction: number } | null>(null);
  const [settings, setSettings] = useState<Record<string, string>>({});
  const current = plan.current?.tier === "custom" ? plan.current.custom_model : null;

  /** The filled-in answer settings, or null when one is out of range. */
  const sampling = (): Record<string, number> | null | "invalid" => {
    const out: Record<string, number> = {};
    for (const field of SAMPLING_FIELDS) {
      const raw = (settings[field.key] ?? "").trim();
      if (!raw) continue;
      const value = Number(raw);
      const whole = field.step === "1" ? Number.isInteger(value) : true;
      if (!Number.isFinite(value) || value < field.min || value > field.max || !whole) {
        onMessage(`Check the answer setting "${field.label}". Nothing was started.`);
        document.getElementById(`${id}-${field.key}`)?.focus();
        return "invalid";
      }
      out[field.key] = value;
    }
    return Object.keys(out).length ? out : null;
  };
  const models = plan.my_models.filter((f) => f.kind === "model");
  const addonFor = (model: MyModelFile) =>
    plan.my_models.find((f) => f.kind === "image_addon" && f.for_model === model.sha256) ?? null;

  const use = useMutation({
    mutationFn: ({
      model,
      addon,
      tuned,
    }: {
      model: MyModelFile;
      addon: MyModelFile | null;
      tuned: Record<string, number> | null;
    }) => api.useMyModel(model.sha256, addon?.sha256 ?? null, tuned),
    onMutate: ({ model }) =>
      onMessage(`Starting ${model.name} in the private AI service. This can take a minute.`),
    onSuccess: (next, { model }) => {
      queryClient.setQueryData(["ai-plan"], next);
      onMessage(`${model.name} is in use. AI features are on.`);
      for (const key of [["ai-runtime"], ["suggestion-status"], ["ai-preferences"]]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
    onError: (error) =>
      onMessage(error instanceof Error ? error.message : "Your model could not start."),
  });
  const copy = useMutation({
    mutationFn: async (tuned: Record<string, number> | null) => {
      const modelFile = modelInput.current?.files?.[0];
      if (!modelFile) throw new Error("Choose a model file (GGUF) first.");
      const addonFile = addonInput.current?.files?.[0] ?? null;
      setProgress({ label: "Copying the model file", fraction: 0 });
      const model = await api.copyMyModel(modelFile, "model", (fraction) =>
        setProgress({ label: "Copying the model file", fraction }),
      );
      let addon: MyModelFile | null = null;
      if (addonFile) {
        onMessage("Copying the image add-on file.");
        setProgress({ label: "Copying the image add-on file", fraction: 0 });
        addon = await api.copyMyModel(
          addonFile,
          "image_addon",
          (fraction) => setProgress({ label: "Copying the image add-on file", fraction }),
          model.sha256,
        );
      }
      return { model, addon, tuned };
    },
    onMutate: () => onMessage("Copying the model file. You can keep using Axcess."),
    onSuccess: (files) => {
      setProgress(null);
      use.mutate(files);
    },
    onError: (error) => {
      setProgress(null);
      onMessage(error instanceof Error ? error.message : "The file could not be copied.");
    },
  });
  const busy = disabled || copy.isPending || use.isPending;
  const percent = progress ? Math.floor(progress.fraction * 100) : 0;

  return (
    <Card className="px-4 py-4 text-sm leading-6 text-fg">
      <h2 className="font-semibold">Use your own model</h2>
      <p className="mt-2">
        To try a model that is not one of the sizes. Choose a model file (GGUF) on this
        computer. Axcess copies it into its AI folder and runs it in the same private AI
        service, which cannot reach the internet. Thinking (reasoning) stays off.
      </p>
      <p className="mt-2">
        Axcess cannot check where the file came from, what licence it has, or how good its
        answers are. Check every answer.
      </p>
      {current && <p className="mt-2 font-semibold">{`In use now: ${current.tag}.`}</p>}

      <details className="mt-3">
        <summary className="min-h-target cursor-pointer content-center font-semibold">
          Answer settings (sampling), optional
        </summary>
        <p id={`${id}-sampling-hint`} className="text-xs leading-5 text-fg-muted">
          Copy these from the model&rsquo;s own page, where its makers list recommended
          settings. Leave them all empty to use Axcess&rsquo;s setting: randomness 0, the most
          predictable answers. Once you fill in any, an empty one uses llama.cpp&rsquo;s
          default. They apply to the next model you start here.
        </p>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          {SAMPLING_FIELDS.map((field) => (
            <div key={field.key}>
              <label htmlFor={`${id}-${field.key}`} className="block">
                {field.label}
              </label>
              <input
                id={`${id}-${field.key}`}
                type="number"
                inputMode="decimal"
                min={field.min}
                max={field.max}
                step={field.step}
                value={settings[field.key] ?? ""}
                onChange={(event) =>
                  setSettings((now) => ({ ...now, [field.key]: event.target.value }))
                }
                aria-describedby={`${id}-sampling-hint`}
                disabled={busy}
                className="mt-1 block min-h-target w-full rounded-xs border border-border-strong bg-surface px-2 text-sm"
              />
            </div>
          ))}
        </div>
      </details>

      <form
        className="mt-3 space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (busy) return;
          const tuned = sampling();
          if (tuned !== "invalid") copy.mutate(tuned);
        }}
      >
        <div>
          <label htmlFor={`${id}-model`} className="block font-semibold">
            Model file (GGUF)
          </label>
          <input
            ref={modelInput}
            id={`${id}-model`}
            type="file"
            accept=".gguf"
            required
            disabled={busy}
            className="mt-1 block min-h-target w-full max-w-full text-sm"
          />
        </div>
        <div>
          <label htmlFor={`${id}-addon`} className="block font-semibold">
            Image add-on file (mmproj GGUF), optional
          </label>
          <p id={`${id}-addon-hint`} className="text-xs leading-5 text-fg-muted">
            Lets the model look at images. Without it, the model answers from text only.
          </p>
          <input
            ref={addonInput}
            id={`${id}-addon`}
            type="file"
            accept=".gguf"
            aria-describedby={`${id}-addon-hint`}
            disabled={busy}
            className="mt-1 block min-h-target w-full max-w-full text-sm"
          />
        </div>
        {progress && (
          <div>
            <p id={`${id}-progress`} className="font-semibold">
              {progress.label}
            </p>
            <progress
              aria-labelledby={`${id}-progress`}
              max={100}
              value={percent}
              className="mt-1 h-3 w-full accent-umich-blue"
            />
            <p className="text-xs text-fg-muted">{percent}%</p>
          </div>
        )}
        <Button type="submit" aria-disabled={busy || undefined}>
          Copy and use this model
        </Button>
      </form>

      {models.length > 0 && (
        <div className="mt-4">
          <h3 className="font-semibold">Models copied before</h3>
          <ul className="mt-1 space-y-2">
            {models.map((model) => {
              const addon = addonFor(model);
              const inUse = current?.gguf.sha256 === model.sha256;
              return (
                <li key={model.sha256} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="break-all">
                    {`${model.name} · ${formatBytes(model.size + (addon?.size ?? 0))} · `}
                    {addon ? "reads images" : "text only"}
                  </span>
                  {inUse ? (
                    <span className="font-semibold">In use now</span>
                  ) : (
                    <Button
                      type="button"
                      aria-disabled={busy || undefined}
                      onClick={() => {
                        if (busy) return;
                        const tuned = sampling();
                        if (tuned !== "invalid") use.mutate({ model, addon, tuned });
                      }}
                    >
                      {`Use ${model.name}`}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Card>
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
        {tier.min_memory_gb} GB memory · {formatBytes(tier.download_bytes)} download.
        {tooSmall &&
          " This computer has less memory than this size needs, so it may be slow or fail."}
        {!tooSmall &&
          !tier.fits &&
          " There may not be enough free disk space for this size."}
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
