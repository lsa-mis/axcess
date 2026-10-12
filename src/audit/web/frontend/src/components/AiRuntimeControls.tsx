import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAiRuntime, startAiRuntime } from "../api/client";
import { AI_ISOLATION_REASON_LABEL, AI_RUNTIME_START_LABEL } from "../lib/terms";
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
 */
export function AiRuntimeControls({ setupPage = false }: { setupPage?: boolean }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const runtime = useQuery({
    queryKey: ["ai-runtime"], queryFn: getAiRuntime, retry: false,
    refetchInterval: 5000,
  });
  const start = useMutation({
    mutationFn: startAiRuntime,
    onMutate: () => setMessage("Starting the AI service. You can keep browsing."),
    onSuccess: (result) => {
      const reason = result.reason ? AI_ISOLATION_REASON_LABEL[result.reason] : null;
      const size = result.download_bytes !== null
        ? ` Download size: about ${(result.download_bytes / 1e9).toFixed(1)} GB.` : "";
      setMessage(`${reason ?? AI_RUNTIME_START_LABEL[result.state]}${size}`);
      void queryClient.invalidateQueries({ queryKey: ["ai-runtime"] });
      void queryClient.invalidateQueries({ queryKey: ["suggestion-status"] });
    },
    onError: () => setMessage("The AI service could not start. Try again or check AI settings."),
  });
  const reason = runtime.data?.reason;
  return <div className="mt-3 space-y-2 text-sm leading-6 text-fg">
    <p>{runtime.data?.running && runtime.data.isolated
      ? "AI service: isolated, local only"
      : reason ? AI_ISOLATION_REASON_LABEL[reason] ?? "AI service is not running."
        : runtime.isError ? "AI service status could not be loaded."
          : "AI service is not running."}</p>
    <p>Axcess starts only its own private AI service. It does not start or stop your own Ollama.</p>
    <Button type="button" aria-disabled={start.isPending || undefined}
      onClick={() => { if (!start.isPending) start.mutate(); }}>
      Start AI service
    </Button>
    <p role="status" className={message ? "" : "sr-only"}>{message}</p>
    {!setupPage && <LinkButton to="/settings/ai">Choose an AI download</LinkButton>}
  </div>;
}
