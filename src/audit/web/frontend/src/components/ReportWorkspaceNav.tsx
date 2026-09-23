import { useLocation } from "react-router";
import Tabs from "./Tabs";

/**
 * Report navigation: overview, the issue table, and change verification.
 *
 * These are three *views of the same report*, not three steps of a task. An
 * early numbered-pill treatment read as a wizard ("1 Overview → 2 Issues →
 * 3 Verify changes") and implied an order and a completion state the report
 * does not have. The segmented row below carries no sequence, and it is the
 * same `Tabs` component the inspector and the tracker use, so the same
 * control reads the same way everywhere in the app.
 *
 * Only the views themselves render this (see ``ReportHeader``), so the
 * active tab is read from the path alone.
 */
export default function ReportWorkspaceNav({
  scanId,
  previousScanId,
}: {
  scanId: number;
  previousScanId: number | null;
}) {
  const { pathname } = useLocation();
  const report = `/scans/${scanId}`;
  const active = /\/scans\/\d+\/diff(\/|$)/.test(pathname)
    ? "diff"
    : /^\/scans\/\d+\/?$/.test(pathname)
      ? "overview"
      : "issues";

  return (
    <Tabs
      mode="nav"
      attached
      label="Report workspace"
      className="mt-0"
      value={active}
      items={[
        { key: "overview", label: "Overview", to: report },
        { key: "issues", label: "Issues", to: `${report}/issues` },
        {
          key: "diff",
          label: "Verify changes",
          to: `${report}/diff${previousScanId != null ? `?compare_to=${previousScanId}` : ""}`,
        },
      ]}
    />
  );
}
