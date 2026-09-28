import Link from "next/link";
import { ArrowUpRight, FileText } from "lucide-react";
import type { Workflow } from "@/lib/types";
import { dateTime, shortId, titleCase } from "@/lib/format";
import { Empty, Status } from "./ui";
export function WorkflowTable({
  rows,
  compact = false,
}: {
  rows: Workflow[];
  compact?: boolean;
}) {
  if (!rows.length)
    return (
      <Empty
        title="Nothing here yet"
        text="Requests will appear here as they move through your workflow."
        action={
          <Link className="button secondary small" href="/requests/new">
            Create a request
          </Link>
        }
      />
    );
  return (
    <div className="table-scroll">
      <table className="data-table workflow-table">
        <thead>
          <tr>
            <th>Request</th>
            <th>Status</th>
            {!compact && <th>Type</th>}
            <th>Created</th>
            <th>
              <span className="sr-only">Open request</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <div className="request-cell">
                  <span className="table-icon">
                    <FileText size={18} />
                  </span>
                  <div>
                    <Link href={`/workflows/${row.id}`}>{row.title}</Link>
                    <span className="cell-meta">
                      FP-{shortId(row.id)} <span>·</span> Revision{" "}
                      {row.revision}
                    </span>
                  </div>
                </div>
              </td>
              <td>
                <Status value={row.status} />
              </td>
              {!compact && (
                <td className="muted">
                  {row.workflow_type
                    ? titleCase(row.workflow_type)
                    : "Being classified"}
                </td>
              )}
              <td className="muted nowrap">{dateTime(row.created_at)}</td>
              <td>
                <Link
                  className="row-link"
                  href={`/workflows/${row.id}`}
                  aria-label={`Open ${row.title}`}
                >
                  <ArrowUpRight size={17} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
