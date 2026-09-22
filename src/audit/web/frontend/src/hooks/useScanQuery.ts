import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ScanDetail } from "../api/types";
import { useProtectedIdentityPartition } from "./useProtectedIdentityContext";

/**
 * The one query key for a scan summary, shared by every report surface.
 *
 * Partitioned by the current opaque proxy identity, for the same reason
 * ProtectedReportGate partitions its own lookup: a changed proxy session
 * must not reuse a previous user's cached report summary. Routes used to
 * key this on `["scan", id]` alone, which both missed that partition and
 * gave each route a cache entry the gate had already populated.
 */
export function scanQueryKey(id: number, identityPartition: string) {
  return ["scan", id, "identity", identityPartition] as const;
}

/**
 * Load a report's summary, reusing whatever the gate already fetched.
 *
 * Every report route sits behind ProtectedReportGate, which fetches this
 * same record to decide whether the report is protected. Keying both on
 * the same partition means the route reads it from cache instead of
 * asking the server again: it removes one request per report page view.
 *
 * Deliberately not gated on `isChecking`. The identity context refetches
 * every 15 seconds, and disabling this query on each of those would make
 * it stale and refetch on every cycle. The fingerprint itself is held
 * steady across a pending refresh, so the key does not churn either. The
 * gate still owns the decision about what may render before identity is
 * confirmed; this hook only runs inside children the gate has admitted.
 */
export function useScanQuery(
  id: number,
  options?: Pick<
    UseQueryOptions<ScanDetail>,
    "refetchInterval" | "refetchIntervalInBackground" | "refetchOnWindowFocus"
  >,
) {
  const identityPartition = useProtectedIdentityPartition();
  return useQuery<ScanDetail>({
    queryKey: scanQueryKey(id, identityPartition),
    queryFn: () => api.getScan(id),
    enabled: Number.isSafeInteger(id) && id > 0,
    // Only the refetch cadence is configurable. The key and the fetcher are
    // fixed, because sharing one cache entry across the gate and the routes
    // is the point of this hook. A route that polls while a scan runs
    // (ScanDetail) passes its interval here rather than opening a second
    // query against the same record.
    ...options,
  });
}
