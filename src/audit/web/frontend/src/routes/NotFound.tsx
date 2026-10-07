import { Link, useLocation } from "react-router";
import { EmptyState } from "../components/ui";

export default function NotFoundRoute() {
  const loc = useLocation();
  return (
    <EmptyState
      level={1}
      title="Page not found"
      message={
        <>
          There is no page at <code>{loc.pathname}</code>. Check the address,
          or choose a page from the menu. You can also go to the{" "}
          <Link to="/scans" className="font-semibold text-umich-blue">
            reports
          </Link>
          .
        </>
      }
    />
  );
}
