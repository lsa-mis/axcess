import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

/**
 * One namespace for every browser-visible protected query and mutation.
 *
 * Keeping the namespace explicit lets an identity change evict only
 * protected state, without disrupting the public-report workspace that may
 * be open in the same local Axcess session.
 */
export const PROTECTED_CLIENT_CACHE_PREFIX = "protected";

export function protectedQueryKey(...parts: readonly unknown[]) {
  return [PROTECTED_CLIENT_CACHE_PREFIX, ...parts] as const;
}

export function protectedMutationKey(...parts: readonly unknown[]) {
  return [PROTECTED_CLIENT_CACHE_PREFIX, ...parts] as const;
}

const IDENTITY_CONTEXT_QUERY_KEY = protectedQueryKey("identity-context");
const LEGACY_PROTECTED_QUERY_PREFIXES = new Set([
  "protected-scan",
  "protected-scans",
  "protected-companion",
  "protected-manual-checks",
  "protected-issue-index",
]);

function isProtectedClientKey(key: readonly unknown[] | undefined): boolean {
  const first = key?.[0];
  return (
    first === PROTECTED_CLIENT_CACHE_PREFIX ||
    (typeof first === "string" && LEGACY_PROTECTED_QUERY_PREFIXES.has(first))
  );
}

function isIdentityContextKey(key: readonly unknown[] | undefined): boolean {
  return key?.[0] === PROTECTED_CLIENT_CACHE_PREFIX && key[1] === "identity-context";
}

function hasProtectedScanMetadata(data: unknown): boolean {
  if (typeof data !== "object" || data === null || !("protection" in data)) {
    return false;
  }
  const protection = data.protection;
  return (
    typeof protection === "object" &&
    protection !== null &&
    "mode" in protection &&
    protection.mode === "protected"
  );
}

/**
 * Remove report data and response-bearing mutations after a proxy identity
 * changes. The identity-context query remains so the new identity can seed
 * fresh, fingerprint-partitioned requests immediately.
 */
function clearProtectedClientState(
  queryClient: ReturnType<typeof useQueryClient>,
): void {
  const isProtectedDataQuery = (key: readonly unknown[], data: unknown) =>
    (isProtectedClientKey(key) && !isIdentityContextKey(key)) ||
    // ``ProtectedReportGate`` performs one generic scan lookup to redirect
    // legacy public URLs. If that lookup has already established protected
    // mode, it belongs to this identity boundary too.
    (key[0] === "scan" && hasProtectedScanMetadata(data));

  void queryClient.cancelQueries({
    predicate: (query) => isProtectedDataQuery(query.queryKey, query.state.data),
  });
  queryClient.removeQueries({
    predicate: (query) => isProtectedDataQuery(query.queryKey, query.state.data),
  });
  for (const mutation of queryClient.getMutationCache().findAll({
    predicate: (candidate) => isProtectedClientKey(candidate.options.mutationKey),
  })) {
    queryClient.getMutationCache().remove(mutation);
  }
}

/** Fallback partition used when no identity has been established. */
export const NO_IDENTITY_PARTITION = "identity-context-unavailable";

/**
 * Read the current identity partition without driving the identity query.
 *
 * `useProtectedIdentityContext` sets `refetchOnMount: "always"`, so every
 * component that calls it triggers another identity request when it mounts.
 * Callers that only need the cache partition -- the report routes, which
 * key their scan query on it -- observe the same entry read-only instead,
 * and leave the refresh policy to the gate that owns it.
 *
 * Still fetches if nothing has fetched yet: `refetchOnMount: false` only
 * suppresses refetching when data is already present.
 */
export function useProtectedIdentityPartition(enabled = true): string {
  const context = useQuery({
    queryKey: IDENTITY_CONTEXT_QUERY_KEY,
    queryFn: api.getProtectedIdentityContext,
    retry: false,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    // The breadcrumb is mounted on every screen, including the dashboard
    // and the scan list, which have no report to partition. Without this
    // it would ask the server for an identity context those screens never
    // use.
    enabled,
  });
  if (context.error) return NO_IDENTITY_PARTITION;
  return context.data?.subject_fingerprint ?? NO_IDENTITY_PARTITION;
}

export interface ProtectedIdentityContext {
  /** Opaque HMAC-derived cache partition, never the proxy subject. */
  fingerprint: string | null;
  /** True only while the current proxy assertion has just been verified. */
  isReady: boolean;
  /** Use this to hide protected content while a focus/poll check is pending. */
  isChecking: boolean;
  error: unknown;
}

/**
 * Verify the current proxy identity before a protected view reads report
 * data. The browser does not cache this response: it is refreshed on mount,
 * focus, reconnect, and a deliberately modest interval. While a refresh is
 * pending consumers must gate protected content, avoiding a stale frame when
 * a shared tab's identity-aware proxy session changes users.
 */
export function useProtectedIdentityContext(): ProtectedIdentityContext {
  const queryClient = useQueryClient();
  const lastFingerprint = useRef<string | null>(null);
  const context = useQuery({
    queryKey: IDENTITY_CONTEXT_QUERY_KEY,
    queryFn: api.getProtectedIdentityContext,
    staleTime: 0,
    gcTime: 0,
    retry: false,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    refetchOnReconnect: "always",
    // This is short enough to bound a same-tab proxy switch while avoiding
    // status-polling pressure on the identity-aware proxy.
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  });

  // Preserve the successful fingerprint while a refresh is pending so that a
  // normal polling cycle does not itself look like an identity change. An
  // error, however, invalidates it immediately and purges protected state.
  const fingerprint = context.error ? null : context.data?.subject_fingerprint ?? null;

  useEffect(() => {
    if (fingerprint === null) {
      if (lastFingerprint.current !== null) {
        clearProtectedClientState(queryClient);
      }
      lastFingerprint.current = null;
      return;
    }
    if (
      lastFingerprint.current !== null &&
      lastFingerprint.current !== fingerprint
    ) {
      clearProtectedClientState(queryClient);
    }
    lastFingerprint.current = fingerprint;
  }, [fingerprint, queryClient]);

  const isChecking = context.isLoading || context.isFetching;
  return {
    fingerprint,
    isReady: fingerprint !== null && !isChecking && !context.error,
    isChecking,
    error: context.error,
  };
}
