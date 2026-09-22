import { AlertOctagon, Check, Loader2 } from "lucide-react";
import type { ScopePreview } from "../../api/types";
import type { ScopePreviewState } from "./useScopePreview";

/**
 * What the crawler will actually do with the address, in a sentence.
 *
 * The old preview printed "Scope:" and a code chip with the host and path,
 * which told an expert what they already knew and told everyone else
 * nothing. This says it: "Will scan lsa.umich.edu/anthro/ and every page
 * under it." It is a status region, so a screen reader hears the answer as
 * it settles; idle renders nothing at all, so there is nothing to announce
 * before the user has typed.
 */
export default function ScopeLine({
  id,
  state,
  data,
  afterSignIn = false,
}: {
  id: string;
  state: ScopePreviewState;
  data: ScopePreview | null;
  afterSignIn?: boolean;
}) {
  if (state === "idle") return <p id={id} role="status" className="sr-only" />;

  if (state === "checking") {
    return (
      <p id={id} role="status" className="mt-1 flex items-start gap-2 text-sm text-fg-muted">
        <Loader2
          className="mt-0.5 h-4 w-4 shrink-0 animate-spin motion-reduce:animate-none"
          aria-hidden
        />
        <span>Checking the address…</span>
      </p>
    );
  }

  if (state === "error" || !data) {
    return (
      <p id={id} role="status" className="mt-1 flex items-start gap-2 text-sm text-sev-critical">
        <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <span>{data?.error ?? "Axcess could not work out what to scan from that address."}</span>
      </p>
    );
  }

  const tail = afterSignIn ? ", after you sign in." : ".";
  return (
    <p id={id} role="status" className="mt-1 flex items-start gap-2 text-sm text-fg">
      <Check className="mt-0.5 h-4 w-4 shrink-0 text-umich-blue" aria-hidden />
      <span>
        <strong>Will scan</strong>{" "}
        {data.whole_host ? (
          <>
            every page on <span className="break-all font-semibold">{data.host}</span>
            {tail}
          </>
        ) : (
          <>
            <span className="break-all font-semibold">
              {data.host}
              {data.path_prefix}
            </span>{" "}
            and every page under it{tail}
            {data.auto_slash_added && (
              <span className="text-fg-muted">
                {" "}
                A trailing slash was added so a sibling path is not included by mistake.
              </span>
            )}
          </>
        )}
      </span>
    </p>
  );
}
