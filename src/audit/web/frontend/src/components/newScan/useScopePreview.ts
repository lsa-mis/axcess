import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { ScopePreview } from "../../api/types";

export type ScopePreviewState = "idle" | "checking" | "ok" | "error";

/**
 * The scope the crawler will actually use for a URL, as the user types it.
 *
 * Debounced at 400 ms: the old 250 ms fired mid-word on any real address,
 * and every fire is a request plus a live-region update. The previous
 * answer stays on screen while the next one loads, so the line never
 * flickers empty between keystrokes; `state` moves to "checking" only for
 * a URL the cache has not seen.
 */
export function useScopePreview(
  url: string,
  wholeHost: boolean,
  scope: string = "public",
): { state: ScopePreviewState; data: ScopePreview | null } {
  const [debounced, setDebounced] = useState(url);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(url), 400);
    return () => window.clearTimeout(timer);
  }, [url]);

  const trimmed = debounced.trim();
  const query = useQuery({
    queryKey: ["scope-preview", trimmed, wholeHost, scope],
    queryFn: () => api.scopePreview(trimmed, wholeHost),
    enabled: Boolean(trimmed),
    placeholderData: keepPreviousData,
    retry: false,
  });

  if (!url.trim()) return { state: "idle", data: null };
  if (query.isPending || (query.isPlaceholderData && query.isFetching) || trimmed !== url.trim()) {
    return { state: "checking", data: query.data ?? null };
  }
  if (query.isError) return { state: "error", data: null };
  if (query.data?.error) return { state: "error", data: query.data };
  return { state: "ok", data: query.data ?? null };
}
