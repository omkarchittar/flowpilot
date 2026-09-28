"use client";
import { useState } from "react";
import { Activity, Check, ChevronRight, ShieldCheck } from "lucide-react";
import type { AuditEvent, AuditPage } from "@/lib/types";
import { dateTime, shortId, titleCase } from "@/lib/format";
import { useResource } from "@/lib/use-resource";
import { Empty, ErrorNotice, Loading, Panel } from "./ui";
export function eventTitle(event: AuditEvent) {
  if (event.event_type === "STATE_CHANGED")
    return titleCase(String(event.payload.to));
  if (event.event_type === "APPROVAL_DECISION")
    return `Decision: ${titleCase(String(event.payload.decision))}`;
  if (event.event_type === "TOOL_CALLED")
    return titleCase(event.tool ?? "Tool executed");
  if (event.event_type === "MODEL_DECISION")
    return `Classified as ${titleCase(String(event.payload.request_type))}`;
  return titleCase(event.event_type);
}
export function AuditView({
  workflowId,
  compact = false,
}: {
  workflowId: string;
  compact?: boolean;
}) {
  const [cursors, setCursors] = useState([0]);
  const after = cursors[cursors.length - 1];
  const resource = useResource<AuditPage>(
    `/workflows/${workflowId}/audit?after=${after}&limit=${compact ? 30 : 50}`,
    5000,
  );
  return (
    <Panel
      title={compact ? "Workflow timeline" : "Audit trail"}
      subtitle={
        compact
          ? "A chronological record of decisions and actions"
          : "Immutable events with correlated actors, requests and evidence"
      }
      action={
        resource.data && (
          <span
            className={`verification ${resource.data.verified ? "verified" : "unverified"}`}
          >
            <ShieldCheck size={14} />
            {resource.data.verified
              ? "Page verified"
              : "Integrity check failed"}
          </span>
        )
      }
    >
      <ErrorNotice message={resource.error} retry={resource.refresh} />
      {!resource.data ? (
        <Loading />
      ) : (
        <>
          {!resource.data.items.length ? (
            <Empty
              title="No events yet"
              text="Events appear as this request is processed."
            />
          ) : (
            <ol className="timeline">
              {resource.data.items.map((event) => (
                <li key={event.id}>
                  <span
                    className={`timeline-marker ${event.event_type === "APPROVAL_DECISION" ? "human" : ""}`}
                  >
                    {event.event_type === "STATE_CHANGED" ? (
                      <Check size={13} />
                    ) : (
                      <Activity size={13} />
                    )}
                  </span>
                  <div className="timeline-event">
                    <div className="timeline-event-heading">
                      <strong>{eventTitle(event)}</strong>
                      <time dateTime={event.created_at}>
                        {dateTime(event.created_at)}
                      </time>
                    </div>
                    <p>
                      {event.actor_id === "system"
                        ? "System"
                        : event.actor_id === "agent"
                          ? "AI assistant"
                          : `User ${shortId(event.actor_id)}`}{" "}
                      <span>·</span> Event {event.sequence}
                      {event.payload.status
                        ? ` · ${String(event.payload.status)}`
                        : ""}
                    </p>
                    <details>
                      <summary>
                        {compact
                          ? "View event details"
                          : "Payload & provenance"}
                        <ChevronRight size={12} />
                      </summary>
                      <dl className="event-meta">
                        <dt>Request</dt>
                        <dd>{event.request_id}</dd>
                        <dt>Event hash</dt>
                        <dd>{event.event_hash}</dd>
                        <dt>Previous hash</dt>
                        <dd>{event.previous_hash}</dd>
                      </dl>
                      <pre className="json-view">
                        {JSON.stringify(event.payload, null, 2)}
                      </pre>
                    </details>
                  </div>
                </li>
              ))}
            </ol>
          )}
          <div className="pagination">
            <span>Verification covers this page and its preceding hash.</span>
            <div className="button-row">
              <button
                className="button small secondary"
                disabled={cursors.length === 1}
                onClick={() => setCursors((all) => all.slice(0, -1))}
              >
                Previous
              </button>
              <button
                className="button small secondary"
                disabled={!resource.data.has_more}
                onClick={() =>
                  setCursors((all) => [...all, resource.data!.next_cursor])
                }
              >
                Next events
              </button>
            </div>
          </div>
        </>
      )}
    </Panel>
  );
}
