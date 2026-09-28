"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { Filter, RefreshCw } from "lucide-react";
import { statusLabels } from "@/lib/format";
import { useResource } from "@/lib/use-resource";
import type { Page, State, Workflow } from "@/lib/types";
import { ErrorNotice, Loading, PageHeading, Pagination, Panel } from "./ui";
import { WorkflowTable } from "./workflow-table";
export function WorkflowList({ approvals = false }: { approvals?: boolean }) {
  const params = useSearchParams();
  const initial = params.get("status");
  const [status, setStatus] = useState(
    approvals
      ? "PENDING_APPROVAL"
      : initial && initial in statusLabels
        ? initial
        : "",
  );
  const [offset, setOffset] = useState(0);
  const limit = 15;
  const resource = useResource<Page<Workflow>>(
    `/workflows?limit=${limit}&offset=${offset}${status ? `&status=${status}` : ""}`,
    6000,
  );
  return (
    <>
      <PageHeading
        eyebrow={approvals ? "Human oversight" : "Vendor operations"}
        title={approvals ? "Approval queue" : "All requests"}
        description={
          approvals
            ? "Check the evidence. Make a decision. Keep the workflow moving."
            : "Follow every request from the first document to its final outcome."
        }
        action={
          <button className="button secondary small" onClick={resource.refresh}>
            <RefreshCw size={15} />
            Refresh
          </button>
        }
      />
      {approvals && (
        <div className="notice info">
          Only an independent approver or administrator can authorize vendor
          creation.
        </div>
      )}
      <Panel>
        <div className="list-toolbar">
          <strong>
            {approvals ? "Awaiting a decision" : "Request directory"}{" "}
            <span className="count-pill">{resource.data?.total ?? "—"}</span>
          </strong>
          {!approvals && (
            <label className="filter-label">
              <Filter size={16} />
              <span className="sr-only">Filter by status</span>
              <select
                aria-label="Filter by status"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">All statuses</option>
                {(Object.keys(statusLabels) as State[]).map((state) => (
                  <option value={state} key={state}>
                    {statusLabels[state]}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <ErrorNotice message={resource.error} retry={resource.refresh} />
        {resource.data ? (
          <>
            <WorkflowTable rows={resource.data.items} />
            <Pagination {...resource.data} onChange={setOffset} />
          </>
        ) : !resource.error ? (
          <Loading />
        ) : null}
      </Panel>
    </>
  );
}
