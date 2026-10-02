import { useState } from "react";
import { Sparkles } from "lucide-react";
import { useAiSetup } from "../hooks/useAiSetup";
import { Button, Card, LinkButton } from "./ui";

const DISMISSED_KEY = "axcess.aiSetupPromptDismissed";

/**
 * Desktop first run: one card above the reports offering the optional AI
 * setup.
 *
 * A card, not a dialog or a step before the app opens: Axcess works fully
 * without AI, so nothing should stand between a person and their first scan.
 * It shows only in the desktop app, only until AI is set up or a download
 * has begun, and "Not now" hides it for good on this computer (Settings >
 * AI features stays). Rejected: a modal on launch, which takes focus the
 * person did not ask to move (WCAG 2.2 SC 3.2.1 On Focus, Level A, is about
 * focus not changing context; paraphrased here as "do not move people
 * somewhere they did not choose") and blocks the page for an optional step.
 * W3C COGA, "Making Content Usable" (https://www.w3.org/TR/coga-usable/):
 * avoid interruptions, and make optional steps clearly optional.
 *
 * The "Not now" and set-up controls sit together after the text, in reading
 * order (WCAG 2.2 SC 2.4.3 Focus Order, Level A).
 */
export default function AiSetupPrompt() {
  const plan = useAiSetup();
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(DISMISSED_KEY) === "1";
    } catch {
      return false;
    }
  });
  if (!plan || dismissed || plan.current || plan.install.state !== "idle") return null;
  return (
    <Card className="mb-5 border-l-4 border-l-umich-blue px-4 py-4 text-sm leading-6 text-fg">
      <h2 className="flex items-center gap-2 font-semibold">
        <Sparkles className="h-4 w-4" aria-hidden />
        Optional: set up AI features
      </h2>
      <p className="mt-1">
        AI can suggest fixes for issues and check images and wording. It runs on this computer, so your
        reports stay here. Setting it up downloads a few gigabytes. You can do it later from Settings.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <LinkButton to="/settings/ai" variant="primary">
          Set up AI features
        </LinkButton>
        <Button
          type="button"
          onClick={() => {
            try {
              localStorage.setItem(DISMISSED_KEY, "1");
            } catch {
              // Private mode: hide it for this visit only.
            }
            setDismissed(true);
          }}
        >
          Not now
        </Button>
      </div>
    </Card>
  );
}
