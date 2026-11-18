import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAiRuntime, startAiRuntime } from "../api/client";
import type { AiPlan, AiRuntimeStatus } from "../api/types";
import { useAiSetup } from "../hooks/useAiSetup";
import {
  AI_ISOLATION_REASON_LABEL,
  AI_MY_MODEL_LABEL,
  AI_RUNTIME_START_LABEL,
  AI_STATE_LABEL,
  AI_TIER_LABEL,
  type AiStateKind,
} from "../lib/terms";
import { Button } from "./ui";

/** A setup is saved and every file it needs is on this computer. */
export function aiIsSetUp(plan: AiPlan): boolean {
  const current = plan.current;
  if (!current) return false;
  if (current.source === "system") return true;
  if (current.tier === "custom") return current.custom_model !== null;
  return plan.tiers.some((tier) => tier.id === current.tier && tier.installed);
}

/** The model in use when it is your own, by the name in its file. */
export function ownModelName(plan: AiPlan): string | null {
  const sha = plan.current?.custom_model?.gguf.sha256;
  return plan.my_models.find((f) => f.sha256 === sha)?.name ?? null;
}

/** "the Standard size", or "your own model (Qwen3.8 4B, text only)". */
function modelsInUse(plan: AiPlan): string {
  const current = plan.current;
  if (!current) return "";
  if (current.tier === "custom") {
    const name = ownModelName(plan) ?? "a GGUF file";
    return `${AI_MY_MODEL_LABEL.toLowerCase()} (${name}${current.vision_model ? "" : ", text only"})`;
  }
  return `the ${AI_TIER_LABEL[current.tier] ?? current.tier} size`;
}

const capitalise = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/**
 * The AI's state in one line, and the one action that state needs. Used on
 * Settings, on the AI features page and on a suggestion that could not run,
 * so the same state reads and works the same everywhere (WCAG 2.2 SC 3.2.4
 * Consistent Identification, Level AA).
 *
 * Why one state (developer, 2026-11-18): the screens showed three facts
 * separately: "AI features are off", "AI service is not running", and
 * whether a size was downloaded. They offered "Start AI service" while AI
 * was off and nothing was downloaded, a button that could only reply with
 * an error. Now the state is one of five (lib/terms.ts AI_STATE_LABEL), and
 * "Start AI again" appears only when AI is on and set up but its service has
 * stopped, the one case where starting it can work. Rejected: keeping the
 * service line and disabling the button when it cannot work, because a
 * disabled button cannot be reached by keyboard or explain itself (W3C COGA
 * Making Content Usable, https://www.w3.org/TR/coga-usable/, paraphrased:
 * do not offer controls that cannot work; repo rule "One control, one job").
 * Turning AI on or off stays on the AI features page, next to setup and
 * removal; this component never downloads anything.
 *
 * After a start the person pressed, the button disappears and focus moves to
 * the state line, which can take focus (tabIndex -1) and is read out there,
 * so focus never falls back to the top of the page (SC 2.4.3 Focus Order,
 * Level A). aria-disabled and a click guard keep focus on the button while
 * it works. The status region (SC 4.1.3 Status Messages, Level AA) says why a
 * start was refused and stays quiet on success, so news is not said twice.
 *
 * While a start loads the models (at launch the app starts AI in the
 * background), the state is "AI is starting" with no button: pressing one
 * would only wait for the same start.
 */
export function AiStatus({ heading = false }: { heading?: boolean }) {
  const queryClient = useQueryClient();
  const plan = useAiSetup();
  const setUp = plan ? aiIsSetUp(plan) : false;
  const enabled = Boolean(plan?.preferences.enabled);
  const ownOllama = plan?.current?.source === "system";
  const runtime = useQuery({
    queryKey: ["ai-runtime"],
    queryFn: getAiRuntime,
    retry: false,
    enabled: setUp && enabled && !ownOllama,
    // Sooner while the models load, so the page moves on soon after.
    refetchInterval: (query) => (query.state.data?.starting ? 2000 : 5000),
  });
  const [message, setMessage] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const lineRef = useRef<HTMLParagraphElement>(null);
  const [focusLine, setFocusLine] = useState(false);
  const start = useMutation({
    mutationFn: startAiRuntime,
    onMutate: () => setMessage("Starting AI. You can keep browsing."),
    onSuccess: (result) => {
      if (result.state === "started" || result.state === "already_running") {
        // Show "AI is on" now, not at the next status check, so focus has
        // somewhere to go when the button disappears.
        queryClient.setQueryData<AiRuntimeStatus>(
          ["ai-runtime"], { running: true, isolated: true, reason: null, starting: false },
        );
        setMessage("");
        setFocusLine(true);
      } else {
        const reason = result.reason ? AI_ISOLATION_REASON_LABEL[result.reason] : null;
        const size = result.download_bytes !== null
          ? ` Download size: about ${(result.download_bytes / 1e9).toFixed(1)} GB.` : "";
        setMessage(`${reason ?? AI_RUNTIME_START_LABEL[result.state]}${size}`);
      }
      void queryClient.invalidateQueries({ queryKey: ["ai-runtime"] });
      void queryClient.invalidateQueries({ queryKey: ["suggestion-status"] });
    },
    onError: () => setMessage("AI could not start. Try again, or check AI features in Settings."),
  });

  const status = runtime.data;
  const kind: AiStateKind = !setUp
    ? "not_set_up"
    : !enabled
      ? "off"
      : ownOllama || (status?.running && status.isolated)
        ? "on"
        : status?.starting
          ? "starting"
          // Before the first status check, say so rather than guess.
          : runtime.isPending ? "on" : "stopped";

  // When a start finishes (the one at launch included), suggestions become
  // available: fetch their status again so a waiting page shows its Suggest
  // buttons without a reload.
  const wasOn = useRef(kind === "on");
  useEffect(() => {
    if (kind === "on" && !wasOn.current) {
      void queryClient.invalidateQueries({ queryKey: ["suggestion-status"] });
    }
    wasOn.current = kind === "on";
  }, [kind, queryClient]);

  useEffect(() => {
    if (focusLine && kind === "on") {
      (headingRef.current ?? lineRef.current)?.focus();
      setFocusLine(false);
    }
  }, [focusLine, kind]);

  if (!plan) return null;
  const models = modelsInUse(plan);
  const ollama = "It uses your own Ollama. Axcess does not start, stop or isolate it.";
  const detail = {
    not_set_up: "Optional AI that suggests fixes and checks images and wording. It runs on this computer.",
    off: ownOllama ? ollama : `${capitalise(models)} is kept on this computer, so turning AI on downloads nothing.`,
    starting: `Loading ${models}. This can take a minute.`,
    on: ownOllama
      ? ollama
      : runtime.isPending
        ? "Checking that the AI service is running…"
        : `Using ${models}. It is isolated and stays on this computer.`,
    stopped: status?.reason
      ? AI_ISOLATION_REASON_LABEL[status.reason] ?? "The AI service is not running."
      : runtime.isError ? "The AI state could not be loaded." : "The AI service is not running.",
  }[kind];
  // A heading where the state leads its own card (the AI features page);
  // plain bold text inside another card, under that card's heading.
  return <div className="space-y-2 text-sm leading-6 text-fg">
    {heading
      ? <h2 ref={headingRef} tabIndex={-1} className="font-semibold">{AI_STATE_LABEL[kind]}</h2>
      : <p ref={lineRef} tabIndex={-1} className="font-semibold">{AI_STATE_LABEL[kind]}</p>}
    <p>{detail}</p>
    {/* Low free memory warns instead of refusing (developer, 2026-11-18:
        the operating system makes room). Said in words, with what helps,
        not by colour (WCAG 2.2 SC 1.4.1 Use of Color, Level A). */}
    {kind === "on" && status?.memory_warning && <p>{status.memory_warning}</p>}
    {kind === "stopped" && <Button type="button" aria-disabled={start.isPending || undefined}
      onClick={() => { if (!start.isPending) start.mutate(); }}>
      Start AI again
    </Button>}
    <p role="status" className={message ? "" : "sr-only"}>{message}</p>
  </div>;
}
