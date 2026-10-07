import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { api } from "../api/client";
import { Button, Card, PageHeader } from "../components/ui";

/**
 * First launch offers two named actions with no preselected download consent.
 * Both use native shared buttons in reading order, not a dialog or a forced
 * install wizard. The person can skip AI and retain all regular checks.
 * WCAG 2.2 SC 2.4.3 Focus Order, Level A; W3C COGA "Making Content Usable",
 * https://www.w3.org/TR/coga-usable/ (paraphrased: make choices clear and
 * explain consequences). Setup leads to the existing size/download page:
 * the choice alone never starts a download.
 * While saving, aria-disabled plus a click guard prevents duplicate choices
 * without blurring the focused button if saving fails (SC 2.4.3, Level A).
 */
export default function AiWelcome() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const choice = useMutation({
    mutationFn: async (setup: boolean) => {
      const preferences = await api.setAiEnabled(false);
      return { setup, preferences };
    },
    onSuccess: ({ setup, preferences }) => {
      queryClient.setQueryData(["ai-preferences"], preferences);
      void queryClient.invalidateQueries({ queryKey: ["ai-plan"] });
      navigate(setup ? "/settings/ai" : "/scans", { replace: true });
    },
  });
  return <div className="mx-auto max-w-3xl">
    <PageHeader title="Choose whether to use AI features" />
    <Card className="space-y-4 px-4 py-4 text-sm leading-6 text-fg">
      <p>AI is optional. Axcess can check your site without it.</p>
      <p>
        AI can suggest fixes and review images and wording. It runs on this computer;
        your reports are not sent to a model service. It can be wrong. A person must
        check each result, and a scan never proves a site meets WCAG.
      </p>
      <p>
        Setting up AI downloads several gigabytes from GitHub and the Ollama model library.
        You choose the size and confirm the download on the next page. You can turn AI on
        or off later in Settings → AI features.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={() => {
          if (!choice.isPending) choice.mutate(true);
        }} aria-disabled={choice.isPending || undefined}>
          Set up AI features
        </Button>
        <Button type="button" onClick={() => {
          if (!choice.isPending) choice.mutate(false);
        }} aria-disabled={choice.isPending || undefined}>
          Continue without AI
        </Button>
      </div>
      {choice.isPending && <p role="status">Saving your choice…</p>}
      {choice.error && <p role="alert">
        {choice.error instanceof Error ? choice.error.message : "Your choice could not be saved."}
      </p>}
    </Card>
  </div>;
}
