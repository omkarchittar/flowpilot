import Link from "next/link";
export default function NotFound() {
  return (
    <div className="full-state">
      <h1>Page not found</h1>
      <p>This address does not point to a FlowPilot page.</p>
      <Link className="button" href="/">
        Back to overview
      </Link>
    </div>
  );
}
