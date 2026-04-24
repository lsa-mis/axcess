import { Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import DashboardRoute from "./routes/Dashboard";
import ScansRoute from "./routes/Scans";
import ScanDetailRoute from "./routes/ScanDetail";
import NewScanRoute from "./routes/NewScan";
import FindingsRoute from "./routes/Findings";
import FindingDetailRoute from "./routes/FindingDetail";
import DiffRoute from "./routes/Diff";
import NotFoundRoute from "./routes/NotFound";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardRoute />} />
        <Route path="/scans" element={<ScansRoute />} />
        <Route path="/scans/new" element={<NewScanRoute />} />
        <Route path="/scans/:scanId" element={<ScanDetailRoute />} />
        <Route path="/scans/:scanId/findings" element={<FindingsRoute />} />
        <Route path="/scans/:scanId/diff" element={<DiffRoute />} />
        <Route path="/findings/:findingId" element={<FindingDetailRoute />} />
        <Route path="*" element={<NotFoundRoute />} />
      </Routes>
    </AppShell>
  );
}
