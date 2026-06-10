import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import DashboardRoute from "./routes/Dashboard";
import IssueDetailRoute from "./routes/IssueDetail";
import IssuesRoute from "./routes/Issues";
import { ReportsRoute, SearchRoute, SettingsRoute } from "./routes/Misc";
import SitesRoute from "./routes/Sites";
import TestRunnerRoute from "./routes/TestRunner";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardRoute />} />
        <Route path="/sites" element={<SitesRoute />} />
        <Route path="/runner" element={<TestRunnerRoute />} />
        <Route path="/issues" element={<IssuesRoute />} />
        <Route path="/issues/:issueId" element={<IssueDetailRoute />} />
        <Route path="/reports" element={<ReportsRoute />} />
        <Route path="/settings" element={<SettingsRoute />} />
        <Route path="/search" element={<SearchRoute />} />
      </Routes>
    </AppShell>
  );
}
