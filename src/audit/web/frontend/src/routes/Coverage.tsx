import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import ChecksView from "../components/coverage/ChecksView";
import FoundView from "../components/coverage/FoundView";
import Tabs from "../components/Tabs";
import { PageHeader } from "../components/ui";

/**
 * Coverage: what Axcess can check, and what it found in your reports.
 *
 * Two parts behind one sidebar entry, switched by the shared Tabs row in `nav`
 * mode: each part is its own URL (/coverage and /coverage/found), so the row is
 * links with aria-current="page", not the ARIA tab widget, which is for panels
 * inside one page (components/Tabs.tsx explains the one keyboard model). The
 * sidebar has one Coverage entry, not one per part, so one control does one
 * job (W3C COGA "Making Content Usable", paraphrased).
 *
 * Rejected names: "Coverage report" for the second part. In Axcess a report is
 * one completed scan (docs/plain-language.md), so a page adding up many scans
 * must not also be called a report. "What Axcess checks" and "What Axcess
 * found" use matching verbs so the difference (from the code, from your scans)
 * is in the names.
 *
 * Both parts are built on this computer; nothing is sent anywhere.
 */
export default function CoverageRoute({ view }: { view: "checks" | "found" }) {
  // The checks part shows how many occurrences each criterion has in your
  // reports; it reads the same all-reports count the found part shows.
  const found = useQuery({
    queryKey: ["coverage-found", "all"],
    queryFn: () => api.getCoverageFound(),
    enabled: view === "checks",
    refetchOnWindowFocus: "always",
  });
  const foundBySc =
    view === "checks" && found.data
      ? new Map(found.data.found_by_criterion.map((row) => [row.sc, row.count]))
      : null;

  return (
    <>
      <PageHeader title="Coverage" subtitle="What Axcess can check, and what it found in your reports." />
      <Tabs
        mode="nav"
        label="Coverage pages"
        attached
        className="mb-6"
        value={view}
        items={[
          { key: "checks", label: "What Axcess checks", to: "/coverage" },
          { key: "found", label: "What Axcess found", to: "/coverage/found" },
        ]}
      />
      {view === "checks" ? <ChecksView foundBySc={foundBySc} /> : <FoundView />}
    </>
  );
}
