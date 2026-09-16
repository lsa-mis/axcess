import { useLocation } from "react-router";
import Tabs from "./Tabs";

/**
 * Report navigation: overview, the issue table, and change verification.
 *
 * These are three *views of the same report*, not three steps of a task. An
 * early numbered-pill treatment read as a wizard ("1 Overview → 2 Issues →
 * 3 Verify changes") and implied an order and a completion state the report
 * does not have — users asked what they were supposed to have finished in
 * step 1. The fix for that was dropping the numbering and the arrows, not the
 * pill: the segmented row below carries no sequence, and it is now the same
 * `Tabs` component the inspector and the tracker use, so the same control
 * reads the same way everywhere in the app.
 */
export default function ReportWorkspaceNav({
  scanId,
  previousScanId,
}: {
  scanId: number;
  previousScanId: number | null;
}) {
  const { pathname } = useLocation();
  const overview = `/scans/${scanId}`;
  const active = pathname.includes("/issues")
    ? "issues"
    : pathname.includes("/diff")
      ? "diff"
      : "overview";

  return (
    <Tabs
      mode="nav"
      label="Report workspace"
      className="mt-4"
      value={active}
      items={[
        { key: "overview", label: "Overview", to: overview },
        { key: "issues", label: "Issues", to: `${overview}/issues` },
        {
          key: "diff",
          label: "Verify changes",
          to: `${overview}/diff${previousScanId != null ? `?compare_to=${previousScanId}` : ""}`,
        },
      ]}
    />
  );
}
