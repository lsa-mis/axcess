import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAiRuntime, startAiRuntime } from "../api/client";
import type { AiRuntimeStatus } from "../api/types";
import {
  AI_ISOLATION_REASON_LABEL,
  AI_RUNTIME_RUNNING,
  AI_RUNTIME_STARTING,
  AI_RUNTIME_START_LABEL,
} from "../lib/terms";
import { Button, LinkButton } from "./ui";

/**
 * Reuse this service control on both Settings pages: a separate local start,
 * never a hidden download or an automatic restart of someone else's Ollama.
 * Button supplies the shared 44 px target (SC 2.5.5 Target Size, Level AAA).
 * aria-disabled and the click guard keep focus while starting (SC 2.4.3 Focus
 * Order, Level A); the always-present status region announces the result
 * (SC 4.1.3 Status Messages, Level AA). A settings link replaces an inline
 * download here: the existing size choices already show cost and consent,
 * avoiding duplicate controls (W3C COGA Making Content Usable,
 * https://www.w3.org/TR/coga-usable/, paraphrased: help people avoid mistakes).
 *
 * While the service runs, the Start button is gone and one line says so
 * (2026-11-17, the developer's request: the button kept saying "Start AI
 * service" with the service already running). Rejected: a greyed-out
 * (disabled) button, which keyboard users cannot reach and whose reason a
 * screen reader does not hear; and keeping it active, a control with nothing
 * to do (W3C COGA Making Content Usable, https://www.w3.org/TR/coga-usable/,
 * paraphrased: do not offer controls that cannot work). The button comes back
 * if the service stops. After a start the person pressed, focus moves from
 * the vanished button to that line, which can take focus (tabIndex -1) and is
 * read out there, so focus never falls back to the top of the page (SC 2.4.3
 * Focus Order, Level A). The status region stays quiet then, so the news is
 * not said twice.
 *
 * While a start loads the models (the app starts the service in the
 * background at launch), the line says "starting" and there is no Start
 * button: pressing it would only wait for the same start. Before, a page
 * opened right after launch said "not running" and offered Start for a
 * service that was minutes from ready (developer, 2026-11-17). The line is
 * plain text; the page's own status message announces the result.
 */
export function AiRuntimeControls({ setupPage = false }: { setupPage?: boolean }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const runningRef = useRef<HTMLParagraphElement>(null);
  const [focusRunning, setFocusRunning] = useState(false);
  const runtime = useQuery({
    queryKey: ["ai-runtime"], queryFn: getAiRuntime, retry: false,
    // Sooner while the models load, so the page moves on soon after.
    refetchInterval: (query) => (query.state.data?.starting ? 2000 : 5000),
  });
  const start = useMutation({
    mutationFn: startAiRuntime,
    onMutate: () => setMessage("Starting the AI service. You can keep browsing."),
    onSuccess: (result) => {
      if (result.state === "started" || result.state === "already_running") {
        // Show the running line now, not at the next status check, so focus
        // has somewhere to go when the button disappears.
        queryClient.setQueryData<AiRuntimeStatus>(
          ["ai-runtime"], { running: true, isolated: true, reason: null, starting: false },
        );
        setMessage("");
        setFocusRunning(true);
      } else {
        const reason = result.reason ? AI_ISOLATION_REASON_LABEL[result.reason] : null;
        const size = result.download_bytes !== null
          ? ` Download size: about ${(result.download_bytes / 1e9).toFixed(1)} GB.` : "";
        setMessage(`${reason ?? AI_RUNTIME_START_LABEL[result.state]}${size}`);
      }
      void queryClient.invalidateQueries({ queryKey: ["ai-runtime"] });
      void queryClient.invalidateQueries({ queryKey: ["suggestion-status"] });
    },
    onError: () => setMessage("The AI service could not start. Try again or check AI settings."),
  });
  const reason = runtime.data?.reason;
  const running = Boolean(runtime.data?.running && runtime.data.isolated);
  const starting = Boolean(runtime.data?.starting) && !running;

  // When a start finishes (the one at launch included), suggestions become
  // available: fetch their status again so a waiting page shows its Suggest
  // buttons without a reload.
  const wasRunning = useRef(running);
  useEffect(() => {
    if (running && !wasRunning.current) {
      void queryClient.invalidateQueries({ queryKey: ["suggestion-status"] });
    }
    wasRunning.current = running;
  }, [running, queryClient]);

  useEffect(() => {
    if (focusRunning && running) {
      runningRef.current?.focus();
      setFocusRunning(false);
    }
  }, [focusRunning, running]);

  // Your own Ollama: one plain sentence and no Start button, because the
  // button could only reply that Axcess does not manage it. Rejected: the
  // old three sentences plus a button that did nothing, which said the same
  // fact three times (W3C COGA Making Content Usable,
  // https://www.w3.org/TR/coga-usable/, paraphrased: keep text short and do
  // not offer controls that cannot work).
  if (reason === "system_ollama_not_managed") {
    return <p className="mt-3 text-sm leading-6 text-fg">
      Uses your own Ollama. Axcess does not start, stop or isolate it.
    </p>;
  }
  return <div className="mt-3 space-y-2 text-sm leading-6 text-fg">
    {running
      ? <p ref={runningRef} tabIndex={-1} className="font-semibold">{AI_RUNTIME_RUNNING}</p>
      : starting
        ? <p className="font-semibold">{AI_RUNTIME_STARTING}</p>
        : <>
        <p>{reason ? AI_ISOLATION_REASON_LABEL[reason] ?? "AI service is not running."
          : runtime.isError ? "AI service status could not be loaded."
            : "AI service is not running."}</p>
        <Button type="button" aria-disabled={start.isPending || undefined}
          onClick={() => { if (!start.isPending) start.mutate(); }}>
          Start AI service
        </Button>
      </>}
    <p role="status" className={message ? "" : "sr-only"}>{message}</p>
    {!setupPage && <LinkButton to="/settings/ai">Choose an AI download</LinkButton>}
  </div>;
}
