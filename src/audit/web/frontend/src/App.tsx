import { Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import A11yRoute from "./routes/A11y";
import A11yByRuleRoute from "./routes/A11yByRule";
import IssueDetailRoute from "./routes/IssueDetail";
import IssuesRoute from "./routes/Issues";
import DashboardRoute from "./routes/Dashboard";
import ScansRoute from "./routes/Scans";
import ScanDetailRoute from "./routes/ScanDetail";
import NewScanRoute from "./routes/NewScan";
import FindingsRoute from "./routes/Findings";
import GroupedFindingsRoute from "./routes/GroupedFindings";
import FindingDetailRoute from "./routes/FindingDetail";
import DiffRoute from "./routes/Diff";
import TrackingRoute from "./routes/Tracking";
import NotFoundRoute from "./routes/NotFound";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardRoute />} />
        <Route path="/scans" element={<ScansRoute />} />
        <Route path="/scans/new" element={<NewScanRoute />} />
        <Route path="/scans/:scanId" element={<ScanDetailRoute />} />
        <Route path="/scans/:scanId/issues" element={<IssuesRoute />} />
        <Route
          path="/scans/:scanId/issues/:issueKey"
          element={<IssueDetailRoute />}
        />
        <Route path="/scans/:scanId/findings" element={<FindingsRoute />} />
        <Route
          path="/scans/:scanId/findings/grouped"
          element={<GroupedFindingsRoute />}
        />
        <Route path="/scans/:scanId/a11y" element={<A11yRoute />} />
        <Route
          path="/scans/:scanId/a11y/by-rule"
          element={<A11yByRuleRoute />}
        />
        <Route path="/scans/:scanId/diff" element={<DiffRoute />} />
        <Route path="/findings/:findingId" element={<FindingDetailRoute />} />
        <Route path="/tracking" element={<TrackingRoute />} />
        <Route path="*" element={<NotFoundRoute />} />
      </Routes>
    </AppShell>
  );
}
