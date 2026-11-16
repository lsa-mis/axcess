import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useLocation } from "react-router";
import { ApiError, api } from "../api/client";

/**
 * Only the desktop landing page offers the first-launch choice. Deep links
 * and reports stay usable if setup cannot load. A normal page, not a modal,
 * gives one clear choice without a focus trap (WCAG 2.2 SC 2.1.2 No Keyboard
 * Trap, Level A). Existing installs do not repeat onboarding; rejected:
 * prompting on every report visit, an interruption contrary to W3C COGA,
 * https://www.w3.org/TR/coga-usable/ (paraphrased: avoid interruptions).
 */
export default function AiWelcomeGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const landing = location.pathname === "/" || location.pathname === "/scans";
  const preferences = useQuery({
    queryKey: ["ai-preferences"],
    queryFn: api.getAiPreferences,
    retry: false,
  });
  if (landing && preferences.isLoading) return <p role="status">Loading settings…</p>;
  if (landing && preferences.data && !preferences.data.choice_recorded) {
    return <Navigate replace to="/welcome/ai" />;
  }
  const missing = preferences.error instanceof ApiError && preferences.error.status === 404;
  return <>
    {landing && preferences.isError && !missing && (
      <p role="alert" className="mb-4 text-sm text-fg">
        AI settings could not be loaded. You can still read reports and use regular checks.
        Open Settings → AI features to try again.
      </p>
    )}
    {children}
  </>;
}
