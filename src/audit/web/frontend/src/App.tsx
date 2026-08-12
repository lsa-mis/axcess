import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router";
import AppShell from "./components/AppShell";
import ProtectedReportGate from "./components/ProtectedReportGate";

const A11yRoute = lazy(() => import("./routes/A11y"));
const A11yByRuleRoute = lazy(() => import("./routes/A11yByRule"));
const IssueDetailRoute = lazy(() => import("./routes/IssueDetail"));
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
        <Route path="/scans/:scanId/issues" element={<ProtectedReportGate><IssuesRoute /></ProtectedReportGate>} />
        <Route
          path="/scans/:scanId/issues/:issueKey"
          element={<ProtectedReportGate><IssueDetailRoute /></ProtectedReportGate>}
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
