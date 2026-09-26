import { Link, useLocation } from "react-router";
import { EmptyState } from "../components/ui";

export default function NotFoundRoute() {
  const loc = useLocation();
  return (
    <EmptyState
      title="Page not found"
      message={
        <>
          No route matches <code>{loc.pathname}</code>. Use the sidebar to
          navigate, or go back to the{" "}
          <Link to="/scans" className="font-semibold text-umich-blue">
            reports
          </Link>
          .
        </>
      }
    />
  );
}
