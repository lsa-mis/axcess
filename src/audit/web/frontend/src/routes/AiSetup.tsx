import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Pause, Play, Trash2 } from "lucide-react";
import { ApiError, api } from "../api/client";
import type {
  AiInstallStatus,
  AiPlan,
  AiTierId,
  AiTierPlan,
  MyModelFile,
} from "../api/types";
import { Button, Card, Checkbox, LinkButton, PageHeader } from "../components/ui";
import { AiStatus, aiIsSetUp } from "../components/AiStatus";
import { cn } from "../lib/cn";
import {
  AI_INSTALL_STATE_LABEL,
  AI_INSTALL_STEP_LABEL,
  AI_TIER_LABEL,
  AI_MY_MODEL_LABEL,
  AI_TIER_DESCRIPTION,
  aiGpuOnlyLabel,
} from "../lib/terms";

/**
 * Settings > AI features: set up local AI on the desktop app, with consent.
 *
 * Why it looks and works this way (keep these when you change it):
 *
 * - A page of its own, not a row on Settings. Settings rows apply the moment
 *   they are chosen and stay on this computer; this page downloads several
 *   gigabytes. A separate step with one clear download button ("Download Small and turn AI on")
 *   keeps a large download from ever starting by accident. WCAG 2.2 SC 3.3.4
 *   Error Prevention (Legal, Financial, Data), Level AA, does not strictly
 *   cover downloads; we follow its idea (paraphrased: an action with large
 *   consequences can be checked before it is done).
 * - The order follows the task (developer, 2026-11-18). Before AI is set up,
 *   the task is choosing a size: privacy facts, then the choice, then the
 *   download. There is no state card then; it could only say "off" and "not
 *   running" and pushed the choice down. Once AI is set up, the usual task is
 *   turning it on or off, so the shared AI state (components/AiStatus.tsx)
 *   and Turn AI on/off come first, and the size choice moves into a closed
 *   "Change the AI models" (native details, open while a download is under
 *   way). W3C COGA Making Content Usable (https://www.w3.org/TR/coga-usable/,
 *   paraphrased: put the main task first, one idea per chunk).
 * - No "Continue without AI" here. It belongs to the first-launch page
 *   (routes/AiWelcome.tsx), where that choice is asked. Here it saved "off"
 *   and jumped to Reports without saying so, and it did the same job as
 *   Back to Settings: leave without setting up (repo rule "One control, one
 *   job"; W3C COGA, paraphrased: no unexpected change of page).
 * - What leaves the computer is said in plain words before the choice: the
 *   program and models come in; reports never go out. The repo's
 *   plain-language rules (docs/plain-language.md) ask that no privacy fact is
 *   dropped to save space.
 * - The size choice is a native fieldset, legend and radio group, not cards
 *   with ARIA. Arrow keys move between sizes and a screen reader hears the
 *   question first. W3C "Using ARIA", rule 1
 *   (https://www.w3.org/TR/using-aria/#rule1, paraphrased: use the native
 *   element when it has the behaviour you need); WCAG technique H71.
 * - A size this computer has too little memory for is still a choice you
 *   can focus and read, and says why in text, not by colour or by disabling
 *   it: a disabled option cannot be focused or explained. WCAG 2.2 SC 1.4.1
 *   Use of Color, Level A. Memory only warns, with one exception (the
 *   developer's decision, 2026-11-18: "only refuse to start 16 gb and above
 *   on a 8gb laptop"): a computer with 8 GB or less is refused Standard and
 *   Large (the server's tier.refused). In place of the download button, a
 *   line says what the size is for and what this computer has. Any other
 *   size bigger than the computer's memory (Large on 16 GB) can be
 *   downloaded, and the note before the button warns that it may be slow,
 *   so the risk is read before the button is pressed (WCAG 2.2 SC 3.3.2
 *   Labels or Instructions, Level A). Low free memory, which changes from
 *   minute to minute, only warns once AI runs.
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
  const headingId = useId();
  // A saved setup's size that is no longer offered ("small") is not a choice.
  const offered = (id: string | undefined): AiTierId | "custom" | null =>
    id === "custom" || plan.tiers.some((t) => t.id === id) ? (id as AiTierId | "custom") : null;
  const [chosen, setChosen] = useState<AiTierId | "custom" | null>(
    offered(status.tier ?? undefined) ??
      offered(plan.current?.tier) ??
      plan.recommended ??
      plan.tiers[0]?.id ??
      null,
  );
  const [confirmRemove, setConfirmRemove] = useState(false);
  // "Change the AI models" opens by itself only while a download is under
  // way, paused or stopped, so its progress and next step are in sight.
  const [changeOpen, setChangeOpen] = useState(
    status.state === "running" || status.state === "paused" || status.state === "failed",
  );
  // Each message is shown directly under the button it reports on: Turn AI
  // on/off, Download and set up, Copy and use this model. One line at the
  // page top was out of sight when a button further down was pressed, and a
  // refusal for low memory read as unrelated (developer, 2026-11-17).
  const [message, setMessage] = useState("");
  const [modelsMessage, setModelsMessage] = useState("");
  const confirmRef = useRef<HTMLButtonElement>(null);

  const refresh = () => {
    // The service's own line ("AI service is running") too: without it, it
    // kept the old state for up to 5 s after Turn AI off or on.
    void queryClient.invalidateQueries({ queryKey: ["ai-runtime"] });
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
        ? "AI is on. Scan checks still need your choice for each scan."
        : "AI is off. Downloaded models and saved results are kept.");
      refresh();
    },
    onError: (error) => setMessage(
      error instanceof Error ? error.message : "AI settings could not be changed.",
    ),
  });
  const [gpuMessage, setGpuMessage] = useState("");
  const changeGpuOnly = useMutation({
    mutationFn: api.setAiGpuOnly,
    onMutate: () =>
      setGpuMessage(
        enabled ? "Saving. If AI is running, it restarts, which can take a minute…" : "Saving…",
      ),
    onSuccess: (preferences) => {
      queryClient.setQueryData(["ai-preferences"], preferences);
      setGpuMessage(
        enabled
          ? "Saved. If AI was running, it restarted with this setting. The AI state above says whether it is on."
          : "Saved. It applies the next time AI starts.",
      );
      refresh();
    },
    onError: (error) =>
      setGpuMessage(error instanceof Error ? error.message : "The setting could not be saved."),
  });
  const start = useMutation({
    mutationFn: (tier: AiTierId) => api.installAi(tier),
    onSuccess: (next) => {
      queryClient.setQueryData(["ai-install"], next);
      setModelsMessage("Download started.");
      refresh();
    },
    onError: (error) =>
      setModelsMessage(
        error instanceof Error
          ? error.message
          : "The download could not start.",
      ),
  });
  const pause = useMutation({
    mutationFn: api.pauseAiInstall,
    onSuccess: () => {
      setModelsMessage("Download paused. What is already downloaded is kept.");
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: api.removeAi,
    onSuccess: async () => {
      setConfirmRemove(false);
      setModelsMessage("AI features removed.");
      refresh();
      // The Remove button is gone now, so focus moves to the size choice,
      // the next thing to act on, instead of falling back to the page top
      // (WCAG 2.2 SC 2.4.3 Focus Order, Level A). Only once the new plan is
      // here: with nothing set up, the choice leaves "Change the AI models"
      // and is drawn again, which would drop focus set any earlier.
      await queryClient.refetchQueries({ queryKey: ["ai-plan"] });
      requestAnimationFrame(() =>
        document.querySelector<HTMLInputElement>(`input[name="${headingId}-tier"]:checked`)?.focus(),
      );
    },
    onError: () => setModelsMessage("AI features could not be removed. Try again."),
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
          ? "Setup finished. AI is on."
          : status.state === "failed"
            ? `AI setup stopped: ${status.error ?? "unknown problem"}`
            : "";
    if (text && text !== announced.current) {
      announced.current = text;
      setModelsMessage(text);
    }
  }, [status.state, status.step, status.error]);

  const running = status.state === "running";
  const current = plan.current;
  const chosenTier = plan.tiers.find((t) => t.id === chosen);
  const hasDownload =
    status.state === "paused" || status.state === "failed" || running;
  // The chosen size is the private setup in use and every file is here, so
  // there is nothing to download (see the rationale at the button).
  const setUp = aiIsSetUp(plan);
  const chosenIsSetUp =
    chosenTier !== undefined &&
    chosenTier.installed &&
    current?.source === "private" &&
    current.backend === "llama_cpp" &&
    current.tier === chosenTier.id;

  // The models part of the page: the size choice, your own model, the
  // download, and removal. Built once, shown open or inside "Change the AI
  // models" (see the rationale at the top of this file).
  const models = (
    <>
      <fieldset aria-describedby={`${headingId}-hw`} disabled={running}>
        {/* Inside "Change the AI models" the summary already says this, so
            the legend is for screen readers only there; it still names the
            radio group (WCAG technique H71). */}
        <legend className={setUp ? "sr-only" : "text-sm font-semibold text-fg"}>
          Choose the AI models
        </legend>
        <p id={`${headingId}-hw`} className="mt-1 text-xs leading-5 text-fg-muted">
          {hardwareSentence(plan)}
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
              memoryGb={plan.hardware.ai_memory_gb}
              onChoose={() => setChosen(tier.id)}
            />
          ))}
        </div>
        {/* Your own model stays in the same radio group, so one choice
            names the model in use (developer, 2026-11-17), but under a
            divider and its own group name, because it is a different kind
            of choice: a file you have, not a download (developer,
            2026-11-18, option A). A nested fieldset with a legend, not a
            heading: a screen reader says the legend when focus enters the
            option, and the radios still move with the arrow keys as one
            group, since they share a name. WCAG technique H71; W3C "Using
            ARIA", rule 1 (https://www.w3.org/TR/using-aria/#rule1,
            paraphrased: use the native element). The legend floats so it
            sits under the divider instead of on it. */}
        <fieldset className="mt-4 border-t border-border pt-3">
          <legend className="float-left mb-2 w-full text-sm font-semibold text-fg">
            Or use a model file you have
          </legend>
          <div className="clear-left">
            <ModelOption
              name={`${headingId}-tier`}
              value="custom"
              title={AI_MY_MODEL_LABEL}
              note={current?.tier === "custom" ? " (in use now)" : ""}
              description="A model file (GGUF) on this computer, to try a model that is not one of the sizes. Nothing is downloaded."
              checked={chosen === "custom"}
              onChoose={() => setChosen("custom")}
            />
          </div>
        </fieldset>
        {plan.recommended === null && (
          <p className="mt-3 text-xs leading-5 text-fg">
            {plan.tiers[0] && belowMemory(plan, plan.tiers[0])
              ? "This computer has less memory than even the smallest size is for. Small may answer very slowly or stop, or you can try a smaller model file of your own."
              : "This computer has less free disk space than even the smallest size needs. Free up space before you download."}
          </p>
        )}
      </fieldset>

      {chosen === "custom" ? (
        <MyModelPanel
          plan={plan}
          disabled={running}
          message={modelsMessage}
          onMessage={setModelsMessage}
        />
      ) : (
        <>
          {/* Model names and licences are for people who need them (an IT
              check, say), so they sit one press away instead of in every
              size option. Rejected: repeating the model names inside each
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
                    // One model that reads text and images.
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
              <span className="font-semibold">{AI_INSTALL_STATE_LABEL.failed}: </span>
              {status.error}
            </p>
          )}
          {status.state === "paused" && (
            <p className="mt-4 text-sm text-fg">
              {AI_INSTALL_STATE_LABEL.paused}. What is already downloaded is
              kept; resume to carry on.
            </p>
          )}

          <div className="mt-4">
            {running ? (
              <Button type="button" onClick={() => pause.mutate()} disabled={pause.isPending}>
                <Pause className="h-4 w-4" aria-hidden />
                Pause download
              </Button>
            ) : chosenTier?.refused ? (
              // A size for 16 GB or more on a computer with 8 GB or less: no
              // download, and a line that says why and what to do, where the
              // button was (developer, 2026-11-18; see the rationale at the
              // top).
              <p className="min-h-target content-center text-sm font-semibold text-fg">
                {`${AI_TIER_LABEL[chosenTier.id]} is for computers with ${chosenTier.min_memory_gb} GB of memory or more, and this computer has ${memoryHave(plan)}. Choose a smaller size.`}
              </p>
            ) : chosenIsSetUp ? (
              // The chosen size is set up and every file is checked: a line
              // says so where the button was (2026-11-17, the developer's
              // request: after the download the page still offered a
              // download). Rejected: a greyed-out (disabled) button, which
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
              // on the saved size alone would leave no repair action.
              //
              // The download size and what happens after are said before the
              // button and tied to it (aria-describedby), so they are read
              // before it is pressed. The note used to come after the button
              // (WCAG 2.2 SC 3.3.2 Labels or Instructions, Level A). The
              // button names the size and the result, "Download Small and
              // turn AI on", instead of the old "Download and set up", which
              // did not say AI would turn on (repo rule: a button says what
              // it does; developer, 2026-11-18).
              chosenTier && (
                <>
                  <p id={`${headingId}-download`} className="mb-2 text-sm text-fg">
                    {downloadNote(chosenTier, enabled, plan)}
                  </p>
                  <Button
                    type="button"
                    variant="primary"
                    aria-describedby={`${headingId}-download`}
                    onClick={() => start.mutate(chosenTier.id)}
                    disabled={start.isPending || !plan.program.available_for_this_computer}
                  >
                    {status.state === "paused" && status.tier === chosenTier.id ? (
                      <Play className="h-4 w-4" aria-hidden />
                    ) : (
                      <Download className="h-4 w-4" aria-hidden />
                    )}
                    {status.state === "paused" && status.tier === chosenTier.id
                      ? "Resume download"
                      : status.state === "failed" && status.tier === chosenTier.id
                        ? "Try the download again"
                        : enabled
                          ? `Download ${AI_TIER_LABEL[chosenTier.id]} and switch to it`
                          : `Download ${AI_TIER_LABEL[chosenTier.id]} and turn AI on`}
                  </Button>
                </>
              )
            )}
          </div>
          <p role="status" className={modelsMessage ? "mt-2 text-sm font-semibold text-fg" : "sr-only"}>
            {modelsMessage}
          </p>
        </>
      )}

      {!plan.program.available_for_this_computer && (
        <p className="mt-3 text-sm text-fg">
          Axcess has no private AI program for this kind of computer.
          AI stays off. Saved results still work.
        </p>
      )}

      {(current || hasDownload) && !running && !confirmRemove && (
        <div className="mt-4">
          <Button type="button" onClick={() => setConfirmRemove(true)}>
            <Trash2 className="h-4 w-4" aria-hidden />
            Remove AI features
          </Button>
        </div>
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
    </>
  );

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="AI features"
        subtitle="Optional. The AI suggests fixes and checks images and wording, on this computer."
      />
      <div className="space-y-5">
        {setUp && (
          <Card className="px-4 py-4 text-sm leading-6 text-fg">
            <AiStatus heading />
            <p className="mt-2">
              {enabled
                ? "While AI runs, you can ask for fix suggestions. AI checks during a scan stay off until you turn them on for that scan."
                : "No new AI suggestions or model checks run. Regular checks, reading text inside images (OCR), and saved results still work."}
            </p>
            {enabled && <p className="mt-2">
              Turning AI off keeps the models and stops only Axcess’s private AI service. Finish current work first.
            </p>}
            <Button
              className="mt-3"
              type="button"
              onClick={() => {
                if (!changeEnabled.isPending) changeEnabled.mutate(!enabled);
              }}
              disabled={running}
              aria-disabled={changeEnabled.isPending || undefined}
            >
              {enabled ? "Turn AI off" : "Turn AI on"}
            </Button>
            {/* Right under the button it reports on, a refusal for low
                memory included (developer, 2026-11-17: "the error ... should
                appear right above or under the button"; SC 3.3.1 Error
                Identification, Level A; SC 4.1.3 Status Messages, Level AA). */}
            <p role="status" className={message ? "mt-2 font-semibold" : "sr-only"}>
              {message}
            </p>
            {/* How the models use the graphics card (developer, 2026-11-19).
                By default llama.cpp puts what fits on the card and the rest
                in the computer's memory; this box keeps everything on the
                card, which is faster when it fits and does not start when
                it does not. It sits with Turn AI on/off because both change
                how AI runs, not which models are downloaded; the models
                card's Download button would wrongly suggest it needs a
                download. A native checkbox (shared Checkbox: 44 px row,
                SC 2.5.5 Target Size (Enhanced), Level AAA) that saves at
                once: the hint says it restarts AI, so the change of
                context is announced before it happens (SC 3.2.2 On Input,
                Level A), and the result is a status message right under it
                (SC 4.1.3 Status Messages, Level AA). Rejected: a separate
                Save button, a second step for one choice. Shown only where
                a graphics build exists (not on an Intel Mac) and only for
                Axcess's own AI, not your own Ollama. */}
            {plan.program.gpu_build && current?.source === "private" && (
              <div className="mt-3 border-t border-border pt-3">
                <Checkbox
                  checked={plan.preferences.gpu_only}
                  onChange={(value) => {
                    if (!changeGpuOnly.isPending) changeGpuOnly.mutate(value);
                  }}
                  disabled={running || changeGpuOnly.isPending}
                  label={aiGpuOnlyLabel(plan.hardware.accelerator)}
                  hint={gpuOnlyHint(plan)}
                />
                <p role="status" className={gpuMessage ? "mt-1 font-semibold" : "sr-only"}>
                  {gpuMessage}
                </p>
              </div>
            )}
          </Card>
        )}

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

        <Card className="px-4 py-4">
          {setUp ? (
            <details open={changeOpen} onToggle={(e) => setChangeOpen(e.currentTarget.open)}>
              <summary className="min-h-target cursor-pointer content-center text-sm font-semibold text-fg">
                Change the AI models
              </summary>
              <div className="mt-3">{models}</div>
            </details>
          ) : (
            models
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

/**
 * "Your own model": the fourth choice in "Choose the AI models", for trying
 * a GGUF file the catalogue does not offer (developer, 2026-11-17).
 *
 * - One of the model options, not a card of its own. Two places that each
 *   chose the model left the sizes showing "Standard (in use now)" while
 *   your own model ran (developer, 2026-11-17: "the size of AI models should
 *   switch to custom"). One radio group, one model in use, marked "(in use
 *   now)" whichever it is (repo rule "One control, one job"; W3C COGA
 *   Making Content Usable, https://www.w3.org/TR/coga-usable/, paraphrased:
 *   one way to do one thing).
 * - Native file inputs with visible labels, not a drop zone: they work by
 *   keyboard and screen reader everywhere, including the desktop app, which
 *   has no file dialog of its own. W3C "Using ARIA", rule 1
 *   (https://www.w3.org/TR/using-aria/#rule1, paraphrased: use the native
 *   element); WCAG technique H44.
 * - One button copies and starts the model; models copied before are listed
 *   with a "Use <name>" button each, so switching for a comparison needs no
 *   new copy (WCAG 2.2 SC 2.4.6 Headings and Labels, Level AA).
 * - Errors are said in text under the field they belong to, the field is
 *   marked invalid (aria-invalid) and points at that text
 *   (aria-describedby), focus moves to the first one, and each says what to
 *   enter instead, with an example. The form checks itself (noValidate)
 *   rather than the browser's passing tooltip, which disappears and is not
 *   part of the page. WCAG 2.2 SC 3.3.1 Error Identification (Level A) and
 *   SC 3.3.3 Error Suggestion (Level AA); techniques ARIA21 and G85. A file
 *   Axcess refuses (not GGUF, the wrong kind) is reported under the file
 *   field that held it.
 * - Answer settings (sampling) sit in a closed native <details>, opened
 *   when one of them has an error so the error can be seen. The model's own
 *   page gives the values to copy. Labels put the plain phrase first, the
 *   technical name in parentheses, then the allowed range (repo
 *   plain-language rule 3; SC 3.3.2 Labels or Instructions, Level A).
 * - Copy progress is a native <progress> with a visible percent; changes of
 *   step and the result go to the models card's status line under its
 *   buttons (SC 4.1.3 Status Messages, Level AA).
 */
const SAMPLING_FIELDS: {
  key: "temp" | "top-p" | "top-k" | "min-p" | "presence-penalty" | "repeat-penalty";
  label: string;
  min: number;
  max: number;
  step: string;
  example: string;
}[] = [
  { key: "temp", label: "Randomness (temperature), 0 to 2", min: 0, max: 2, step: "any", example: "0.6" },
  { key: "top-p", label: "Word choice by share (top-p), 0 to 1", min: 0, max: 1, step: "any", example: "0.95" },
  { key: "top-k", label: "Word choice by count (top-k), 0 to 1000", min: 0, max: 1000, step: "1", example: "20" },
  { key: "min-p", label: "Least likely word kept (min-p), 0 to 1", min: 0, max: 1, step: "any", example: "0" },
  {
    key: "presence-penalty",
    label: "Penalty for any repeated word (presence penalty), -2 to 2",
    min: -2,
    max: 2,
    step: "any",
    example: "1.5",
  },
  {
    key: "repeat-penalty",
    label: "Penalty for repeating often (repetition penalty), 0 to 2",
    min: 0,
    max: 2,
    step: "any",
    example: "1.1",
  },
];

type FieldKey = "model" | "addon" | (typeof SAMPLING_FIELDS)[number]["key"];

function MyModelPanel({
  plan,
  disabled,
  message,
  onMessage,
}: {
  plan: AiPlan;
  disabled: boolean;
  message: string;
  onMessage: (text: string) => void;
}) {
  const queryClient = useQueryClient();
  const id = useId();
  const modelInput = useRef<HTMLInputElement>(null);
  const addonInput = useRef<HTMLInputElement>(null);
  const settingsBox = useRef<HTMLDetailsElement>(null);
  const [progress, setProgress] = useState<{ label: string; fraction: number } | null>(null);
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const current = plan.current?.tier === "custom" ? plan.current.custom_model : null;
  const fieldId = (key: FieldKey) => `${id}-${key}`;
  const errorId = (key: FieldKey) => `${id}-${key}-error`;

  /** Show one error under its field, mark the field, and move focus there. */
  const showError = (key: FieldKey, text: string) => {
    setErrors({ [key]: text });
    if (key !== "model" && key !== "addon" && settingsBox.current) {
      settingsBox.current.open = true;
    }
    onMessage("Nothing was started. Fix the field marked below.");
    requestAnimationFrame(() => document.getElementById(fieldId(key))?.focus());
  };

  /** The filled-in answer settings, or "invalid" after showing the error. */
  const sampling = (): Record<string, number> | null | "invalid" => {
    const out: Record<string, number> = {};
    for (const field of SAMPLING_FIELDS) {
      const raw = (settings[field.key] ?? "").trim();
      if (!raw) continue;
      const value = Number(raw);
      const whole = field.step === "1" ? Number.isInteger(value) : true;
      if (!Number.isFinite(value) || value < field.min || value > field.max || !whole) {
        showError(
          field.key,
          `Enter a ${field.step === "1" ? "whole number" : "number"} from ${field.min} to ${field.max}, for example ${field.example}. Or leave it empty.`,
        );
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
    onSuccess: (next, { model, addon }) => {
      queryClient.setQueryData(["ai-plan"], next);
      onMessage(
        `${model.name} is in use${addon ? "" : ", for text only"}. AI is on.`,
      );
      for (const key of [["ai-runtime"], ["suggestion-status"], ["ai-preferences"]]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
    onError: (error) => {
      // The server says what happened to the model used before (running
      // again, or not). Refresh so the list and "(in use now)" match it.
      onMessage(
        error instanceof Error
          ? error.message
          : "Your model could not start. Try again, or choose one of the sizes.",
      );
      for (const key of [["ai-plan"], ["ai-runtime"], ["suggestion-status"]]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });
  // Which file was being sent, so a refusal lands under that field.
  const sending = useRef<"model" | "addon">("model");
  const copy = useMutation({
    mutationFn: async ({
      modelFile,
      addonFile,
      tuned,
    }: {
      modelFile: File;
      addonFile: File | null;
      tuned: Record<string, number> | null;
    }) => {
      sending.current = "model";
      setProgress({ label: "Copying the model file", fraction: 0 });
      const model = await api.copyMyModel(modelFile, "model", (fraction) =>
        setProgress({ label: "Copying the model file", fraction }),
      );
      let addon: MyModelFile | null = null;
      if (addonFile) {
        sending.current = "addon";
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
      const text =
        error instanceof Error
          ? error.message
          : "The file could not be copied. Check that it is on this computer and try again.";
      showError(sending.current, text);
    },
  });
  const busy = disabled || copy.isPending || use.isPending;
  const percent = progress ? Math.floor(progress.fraction * 100) : 0;
  const describedBy = (...ids: (string | false)[]) => ids.filter(Boolean).join(" ") || undefined;
  const errorText = (key: FieldKey) =>
    errors[key] ? (
      <p id={errorId(key)} className="mt-1 text-sm font-semibold text-sev-critical">
        {`Error: ${errors[key]}`}
      </p>
    ) : null;

  return (
    <div className="mt-4 text-sm leading-6 text-fg">
      <p>
        Choose a model file (GGUF) on this computer. Axcess copies it into its AI folder
        and runs it in the same private AI service, which cannot reach the internet.
        Thinking (reasoning) stays off.
      </p>
      <p className="mt-2">
        Axcess cannot check where the file came from, what licence it has, how good its
        answers are, or whether it fits in this computer&rsquo;s memory. Check every answer.
      </p>

      <form
        noValidate
        className="mt-3 space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (busy) return;
          const modelFile = modelInput.current?.files?.[0];
          if (!modelFile) {
            showError(
              "model",
              "Choose a model file. Its name ends in .gguf, for example Qwen3-4B-Q4_K_M.gguf.",
            );
            return;
          }
          const tuned = sampling();
          if (tuned === "invalid") return;
          setErrors({});
          copy.mutate({ modelFile, addonFile: addonInput.current?.files?.[0] ?? null, tuned });
        }}
      >
        <div>
          <label htmlFor={fieldId("model")} className="block font-semibold">
            Model file (GGUF)
          </label>
          <input
            ref={modelInput}
            id={fieldId("model")}
            type="file"
            accept=".gguf"
            aria-invalid={errors.model ? true : undefined}
            aria-describedby={describedBy(!!errors.model && errorId("model"))}
            onChange={() => setErrors((now) => ({ ...now, model: undefined }))}
            disabled={busy}
            className="mt-1 block min-h-target w-full max-w-full text-sm"
          />
          {errorText("model")}
        </div>
        <div>
          <label htmlFor={fieldId("addon")} className="block font-semibold">
            Image add-on file (mmproj GGUF), optional
          </label>
          <p id={`${id}-addon-hint`} className="text-xs leading-5 text-fg-muted">
            Lets the model look at images. Without it, the model answers from text only.
          </p>
          <input
            ref={addonInput}
            id={fieldId("addon")}
            type="file"
            accept=".gguf"
            aria-invalid={errors.addon ? true : undefined}
            aria-describedby={describedBy(`${id}-addon-hint`, !!errors.addon && errorId("addon"))}
            onChange={() => setErrors((now) => ({ ...now, addon: undefined }))}
            disabled={busy}
            className="mt-1 block min-h-target w-full max-w-full text-sm"
          />
          {errorText("addon")}
        </div>

        <details ref={settingsBox}>
          <summary className="min-h-target cursor-pointer content-center font-semibold">
            Answer settings (sampling), optional
          </summary>
          <p id={`${id}-sampling-hint`} className="text-xs leading-5 text-fg-muted">
            Copy these from the model&rsquo;s own page, where its makers list recommended
            settings. Leave them all empty to use Axcess&rsquo;s setting: randomness 0, the
            most predictable answers. Once you fill in any, an empty one uses llama.cpp&rsquo;s
            default. They apply to the next model you start here.
          </p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            {SAMPLING_FIELDS.map((field) => (
              <div key={field.key}>
                <label htmlFor={fieldId(field.key)} className="block">
                  {field.label}
                </label>
                <input
                  id={fieldId(field.key)}
                  type="number"
                  inputMode="decimal"
                  min={field.min}
                  max={field.max}
                  step={field.step}
                  value={settings[field.key] ?? ""}
                  onChange={(event) => {
                    const value = event.target.value;
                    setSettings((now) => ({ ...now, [field.key]: value }));
                    setErrors((now) => ({ ...now, [field.key]: undefined }));
                  }}
                  aria-invalid={errors[field.key] ? true : undefined}
                  aria-describedby={describedBy(
                    `${id}-sampling-hint`,
                    !!errors[field.key] && errorId(field.key),
                  )}
                  disabled={busy}
                  className="mt-1 block min-h-target w-full rounded-xs border border-border-strong bg-surface px-2 text-sm"
                />
                {errorText(field.key)}
              </div>
            ))}
          </div>
        </details>

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
        <Button type="submit" variant="primary" aria-disabled={busy || undefined}>
          Copy and use this model
        </Button>
        <p role="status" className={message ? "font-semibold" : "sr-only"}>
          {message}
        </p>
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
                        if (tuned === "invalid") return;
                        setErrors({});
                        use.mutate({ model, addon, tuned });
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
    </div>
  );
}

function TierOption({
  tier,
  name,
  recommended,
  current,
  checked,
  memoryGb,
  onChoose,
}: {
  tier: AiTierPlan;
  name: string;
  recommended: boolean;
  current: boolean;
  checked: boolean;
  memoryGb: number;
  onChoose: () => void;
}) {
  const below = memoryGb > 0 && memoryGb < tier.min_memory_gb;
  return (
    <ModelOption
      name={name}
      value={tier.id}
      title={AI_TIER_LABEL[tier.id] ?? tier.label}
      note={current ? " (in use now)" : recommended ? " (suggested for this computer)" : ""}
      // Each size says the same three things in the same order: what it is
      // like, the memory it is for, and the download (W3C COGA Making
      // Content Usable, https://www.w3.org/TR/coga-usable/, paraphrased:
      // the same pattern for the same thing). "For computers with 16 GB of
      // memory or more" replaces "16 GB memory", which did not say whether
      // it was needed or used (developer, 2026-11-18).
      description={
        `${AI_TIER_DESCRIPTION[tier.id]} For computers with ${tier.min_memory_gb} GB of memory or more. ` +
        `${formatBytes(tier.download_bytes)} download.` +
        (tier.refused
          ? " This computer has less memory than this size is for, so it cannot be used here."
          : below
            ? " This computer has less memory than this size is for, so it may answer very slowly or stop."
            : !tier.fits
            ? " There may not be enough free disk space for this size."
            : "")
      }
      checked={checked}
      onChoose={onChoose}
    />
  );
}

/**
 * One option in "Choose the AI models": a size, or your own model. Shared so
 * every option looks and works the same (WCAG 2.2 SC 3.2.4 Consistent
 * Identification, Level AA): a native radio inside its label, the
 * description tied to it (aria-describedby), and the chosen one marked by a
 * thicker border and a tint, not by colour alone (SC 1.4.1 Use of Color).
 */
function ModelOption({
  name,
  value,
  title,
  note,
  description,
  checked,
  onChoose,
}: {
  name: string;
  value: string;
  title: string;
  note: string;
  description: string;
  checked: boolean;
  onChoose: () => void;
}) {
  const id = useId();
  return (
    <label
      htmlFor={id}
      className={cn(
        "grid min-h-target cursor-pointer grid-cols-[auto_minmax(0,1fr)] gap-x-3 rounded-xs border px-3 py-2.5",
        checked ? "border-2 border-umich-blue bg-surface-muted" : "border-border",
        "has-[:focus-visible]:outline has-[:focus-visible]:outline-[3px] has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-umich-blue",
      )}
    >
      <input
        id={id}
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={onChoose}
        aria-describedby={`${id}-desc`}
        className="row-span-2 mt-1 h-4 w-4 shrink-0 accent-umich-blue"
      />
      <span className="text-sm font-semibold text-fg">
        {title}
        {note}
      </span>
      <span id={`${id}-desc`} className="text-xs leading-5 text-fg-muted">
        {description}
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

/**
 * This computer has less memory than the size is for. Only a warning: the
 * one refusal is the server's tier.refused (8 GB or less, and a size for
 * 16 GB or more). Memory is as computers are sold (the server's
 * hardware.memory_gb), so a 16 GB computer reads 16, not 15, plus a
 * separate graphics card's own memory (ai_memory_gb; developer,
 * 2026-11-19), because the AI uses both. 0 means unknown, which never
 * warns.
 */
function belowMemory(plan: AiPlan, tier: AiTierPlan): boolean {
  return plan.hardware.ai_memory_gb > 0 && plan.hardware.ai_memory_gb < tier.min_memory_gb;
}

/** What the graphics-only box changes, and that changing it restarts AI. */
function gpuOnlyHint(plan: AiPlan): string {
  const card = plan.hardware.gpu_memory_gb;
  const where = plan.hardware.accelerator === "apple" ? "the chip\u2019s graphics" : "the graphics card";
  return (
    `Faster when the models fit in the memory of ${where}. If they do not fit, AI does not start. ` +
    `When this is off, Axcess puts what fits on ${where} and the rest in the computer\u2019s memory. ` +
    (card > 0 ? `This graphics card has ${card} GB of its own memory. ` : "") +
    "Changing this restarts AI if it is on."
  );
}

/**
 * "16 GB", or "16 GB, counting the 8 GB on its graphics card": the figure
 * the sizes are measured against, saying where it comes from when a card
 * adds to it, so it never looks like a wrong reading of the computer's
 * memory. The server's refusal says it the same way.
 */
function memoryHave(plan: AiPlan): string {
  const { ai_memory_gb: total, gpu_memory_gb: card } = plan.hardware;
  return card > 0 ? `${total} GB, counting the ${card} GB on its graphics card` : `${total} GB`;
}

/**
 * The computer, and why a size is suggested. Without a graphics card the
 * suggestion is the smallest size even when a bigger one fits, because
 * bigger models answer slowly there (audit/ai/hardware.py recommend). The
 * page used to leave that unsaid, so "Small (suggested)" read as "Standard
 * does not fit" (developer, 2026-11-18).
 */
function hardwareSentence(plan: AiPlan): string {
  const memory = plan.hardware.ai_memory_gb;
  const card = plan.hardware.gpu_memory_gb;
  const disk = formatBytes(plan.hardware.free_disk_bytes);
  const chip = {
    apple: "an Apple chip",
    nvidia: "an NVIDIA graphics card",
    amd: "an AMD graphics card",
    other: "a graphics card",
    none: "no graphics card Axcess can use",
  }[plan.hardware.accelerator];
  // A separate card's own memory is said, and the total the sizes use, so
  // "Standard: for computers with 16 GB" on an 8 GB laptop with an 8 GB
  // card is not a puzzle (developer, 2026-11-19).
  let sentence =
    card > 0
      ? `This computer has ${plan.hardware.memory_gb} GB of memory, ${disk} of free disk space, and ${chip} with ${card} GB of its own memory. The AI uses both, so the sizes count ${memory} GB.`
      : `This computer has ${plan.hardware.memory_gb} GB of memory, ${disk} of free disk space, and ${chip}.`;
  const suggested = plan.tiers.find((tier) => tier.id === plan.recommended);
  const bigger = plan.tiers.filter(
    (tier) => suggested && tier.min_memory_gb > suggested.min_memory_gb && tier.min_memory_gb <= memory,
  );
  if (suggested && plan.hardware.accelerator === "none" && bigger.length > 0) {
    const names = bigger.map((tier) => AI_TIER_LABEL[tier.id]).join(" and ");
    sentence +=
      ` ${AI_TIER_LABEL[suggested.id]} is suggested because, without a graphics card, bigger sizes take longer to answer.` +
      ` ${names} also ${bigger.length > 1 ? "fit" : "fits"} this computer's memory.`;
  }
  return sentence;
}

/**
 * Said before the download button: the size, what happens after, and a
 * warning when this computer has less memory than the size is for.
 */
function downloadNote(tier: AiTierPlan, enabled: boolean, plan: AiPlan): string {
  const size = `Download size: ${formatBytes(tier.download_bytes)}.`;
  const after = enabled
    ? `${size} Axcess checks each file, then switches AI to ${AI_TIER_LABEL[tier.id]}.`
    : `${size} Axcess checks each file, then turns AI on.`;
  return belowMemory(plan, tier)
    ? `${after} ${AI_TIER_LABEL[tier.id]} is for computers with ${tier.min_memory_gb} GB of memory or more, and this computer has ${memoryHave(plan)}, so it may answer very slowly or stop.`
    : after;
}

function licenceName(spdx: string): string {
  return spdx === "Apache-2.0" ? "Apache 2.0 licence" : `${spdx} licence`;
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${Math.round(bytes / 1e6)} MB`;
  return `${Math.max(0, Math.round(bytes / 1e3))} KB`;
}
