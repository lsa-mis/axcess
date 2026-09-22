/**
 * The route table.
 *
 * Every route is `lazy`, so a screen's code is fetched when it is first
 * visited rather than in the entry bundle. The one Suspense boundary around
 * the whole table is deliberate: a per-route boundary would replace the
 * shell chrome on each navigation, and the shell is what makes a report
 * feel like one place.
 *
 * Report routes are wrapped in ProtectedReportGate. The gate resolves
 * whether a report is protected before its children mount, and sends
 * protected reports to their own workflow, which has permission-aware
 * navigation and no export controls. The protected routes themselves are
 * not wrapped: they are that workflow, and wrapping them would redirect
 * them to themselves.
 *
 * The redirects at the bottom keep links people already have working.
 * Review, manual-checks and handoff were separate screens before the
 * Issues table absorbed them; /scans/protected/new was a separate form
 * before protected scans became a mode of the one New scan form. They are
 * cheap to keep and the alternative is a 404 on a bookmark.
 */
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router";
import AppShell from "./components/AppShell";
import ProtectedReportGate from "./components/ProtectedReportGate";

const A11yRoute = lazy(() => import("./routes/A11y"));
const A11yByRuleRoute = lazy(() => import("./routes/A11yByRule"));
const IssueDetailRoute = lazy(() => import("./routes/IssueDetail"));
const IssuePagesRoute = lazy(() => import("./routes/IssuePages"));
const IssuePageScreenshotsRoute = lazy(() => import("./routes/IssuePageScreenshots"));
const IssuesRoute = lazy(() => import("./routes/Issues"));
const DashboardRoute = lazy(() => import("./routes/Dashboard"));
const ScansRoute = lazy(() => import("./routes/Scans"));
const ScanDetailRoute = lazy(() => import("./routes/ScanDetail"));
const NewScanRoute = lazy(() => import("./routes/NewScan"));
const ProtectedCompanionRoute = lazy(() => import("./routes/ProtectedCompanion"));
const ProtectedManualChecksRoute = lazy(() => import("./routes/ProtectedManualChecks"));
const ProtectedIssueIndexRoute = lazy(() => import("./routes/ProtectedIssueIndex"));
const FindingsRoute = lazy(() => import("./routes/Findings"));
const GroupedFindingsRoute = lazy(() => import("./routes/GroupedFindings"));
const FindingDetailRoute = lazy(() => import("./routes/FindingDetail"));
const DiffRoute = lazy(() => import("./routes/Diff"));
const TrackingRoute = lazy(() => import("./routes/Tracking"));
const PageEvidenceRoute = lazy(() => import("./routes/PageEvidence"));
const InspectorRoute = lazy(() => import("./routes/Inspector"));
const NotFoundRoute = lazy(() => import("./routes/NotFound"));

export default function App() {
  return (
    <AppShell>
      <Suspense fallback={<p className="py-8 text-sm text-fg-muted" role="status">Loading workspace…</p>}>
        <Routes>
        <Route path="/" element={<DashboardRoute />} />
        <Route path="/scans" element={<ScansRoute />} />
        <Route path="/scans/new" element={<NewScanRoute />} />
        <Route path="/scans/protected/new" element={<LegacyProtectedNewRedirect />} />
        <Route path="/scans/:scanId/protected" element={<ProtectedCompanionRoute />} />
        <Route path="/scans/:scanId/protected/manual-checks" element={<ProtectedManualChecksRoute />} />
        <Route path="/scans/:scanId/protected/issues" element={<ProtectedIssueIndexRoute />} />
        <Route path="/scans/:scanId" element={<ProtectedReportGate><ScanDetailRoute /></ProtectedReportGate>} />
        <Route path="/scans/:scanId/review" element={<ProtectedReportGate><LegacyReportRedirect /></ProtectedReportGate>} />
        <Route path="/scans/:scanId/manual-checks" element={<ProtectedReportGate><LegacyReportRedirect /></ProtectedReportGate>} />
        <Route path="/scans/:scanId/handoff" element={<ProtectedReportGate><LegacyReportRedirect /></ProtectedReportGate>} />
        <Route path="/scans/:scanId/pages/:pageId" element={<ProtectedReportGate><PageEvidenceRoute /></ProtectedReportGate>} />
        <Route path="/scans/:scanId/pages/:pageId/inspect" element={<ProtectedReportGate><InspectorRoute /></ProtectedReportGate>} />
        <Route path="/scans/:scanId/issues" element={<ProtectedReportGate><IssuesRoute /></ProtectedReportGate>} />
        <Route
          path="/scans/:scanId/issues/:issueKey"
          element={<ProtectedReportGate><IssueDetailRoute /></ProtectedReportGate>}
        />
        <Route
          path="/scans/:scanId/issues/:issueKey/pages"
          element={<ProtectedReportGate><IssuePagesRoute /></ProtectedReportGate>}
        />
        <Route
          path="/scans/:scanId/issues/:issueKey/pages/:pageId/screenshots"
          element={<ProtectedReportGate><IssuePageScreenshotsRoute /></ProtectedReportGate>}
        />
        <Route path="/scans/:scanId/findings" element={<ProtectedReportGate><FindingsRoute /></ProtectedReportGate>} />
        <Route
          path="/scans/:scanId/findings/grouped"
          element={<ProtectedReportGate><GroupedFindingsRoute /></ProtectedReportGate>}
        />
        <Route path="/scans/:scanId/a11y" element={<ProtectedReportGate><A11yRoute /></ProtectedReportGate>} />
        <Route
          path="/scans/:scanId/a11y/by-rule"
          element={<ProtectedReportGate><A11yByRuleRoute /></ProtectedReportGate>}
        />
        <Route path="/scans/:scanId/diff" element={<ProtectedReportGate><DiffRoute /></ProtectedReportGate>} />
        <Route path="/findings/:findingId" element={<FindingDetailRoute />} />
        <Route path="/tracking" element={<TrackingRoute />} />
        <Route path="*" element={<NotFoundRoute />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}

function LegacyReportRedirect() {
  const { scanId } = useParams<{ scanId: string }>();
  return <Navigate replace to={`/scans/${scanId}/issues`} />;
}

function LegacyProtectedNewRedirect() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  params.set("mode", "login");
  return <Navigate replace to={`/scans/new?${params.toString()}`} />;
}
