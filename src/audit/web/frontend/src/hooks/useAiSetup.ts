import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/**
 * The desktop AI setup, or undefined when this is not the desktop app.
 *
 * Only the desktop app serves `/api/ai/plan`; anywhere else it answers 404
 * and the AI setup links stay hidden, because a shared server's AI is set up
 * by its administrator.
 */
export function useAiSetup() {
  const { data } = useQuery({
    queryKey: ["ai-plan"],
    queryFn: api.getAiPlan,
    retry: false,
    staleTime: 30_000,
  });
  return data;
}
