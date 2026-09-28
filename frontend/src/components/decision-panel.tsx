"use client";
import { useState } from "react";
import { Check, RotateCcw, ShieldCheck, X } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { Decision, WorkflowDetail } from "@/lib/types";
import { useAuth } from "./auth";
import { ErrorNotice, Panel } from "./ui";
export function DecisionPanel({
  workflow,
  onSaved,
}: {
  workflow: WorkflowDetail;
  onSaved: () => void;
}) {
  const { session } = useAuth();
  const [selected, setSelected] = useState<Decision | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const user = session!.user;
  const authorized = ["approver", "admin"].includes(user.role);
  const reviewer = user.role === "reviewer";
  const self = user.id === workflow.requester_id;
  if (workflow.status !== "PENDING_APPROVAL") return null;
  if (!authorized && !reviewer)
    return (
      <div className="notice info">
        <ShieldCheck size={20} />
        <span>
          This request is ready for an independent approver. Vendor creation
          will begin only after their decision.
        </span>
      </div>
    );
  return (
    <Panel
      className="decision-panel"
      title="Your decision"
      subtitle={`Reviewing revision ${workflow.revision}. Actions apply only to this version.`}
    >
      <div className="form-body">
        {self && (
          <p className="notice warning">
            You submitted this request. An independent approver must authorize
            it.
          </p>
        )}
        <div className="decision-options">
          {authorized && (
            <button
              type="button"
              aria-pressed={selected === "approve"}
              className={`decision-option ${selected === "approve" ? "selected" : ""}`}
              disabled={busy || self || !workflow.validation?.ready}
              onClick={() => {
                setSelected("approve");
                setError(undefined);
              }}
            >
              <Check size={19} />
              <strong>Approve</strong>
              <span>Create the vendor and notify the requester.</span>
            </button>
          )}
          <button
            type="button"
            aria-pressed={selected === "request_changes"}
            className={`decision-option ${selected === "request_changes" ? "selected" : ""}`}
            disabled={busy}
            onClick={() => {
              setSelected("request_changes");
              setError(undefined);
            }}
          >
            <RotateCcw size={18} />
            <strong>Request changes</strong>
            <span>Return it for an updated request or evidence.</span>
          </button>
          {authorized && (
            <button
              type="button"
              aria-pressed={selected === "reject"}
              className={`decision-option ${selected === "reject" ? "selected" : ""}`}
              disabled={busy}
              onClick={() => {
                setSelected("reject");
                setError(undefined);
              }}
            >
              <X size={18} />
              <strong>Reject</strong>
              <span>Close this request without creating a vendor.</span>
            </button>
          )}
        </div>
        {selected && (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (busy) return;
              setBusy(true);
              setError(undefined);
              try {
                await api(
                  `/workflows/${workflow.id}/decisions`,
                  {
                    method: "POST",
                    body: JSON.stringify({
                      revision: workflow.revision,
                      decision: selected,
                      comment,
                    }),
                  },
                  session!.csrf_token,
                );
                setSelected(null);
                onSaved();
              } catch (cause) {
                setError(errorMessage(cause));
                if (
                  cause instanceof Error &&
                  "status" in cause &&
                  cause.status === 409
                )
                  onSaved();
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Decision note
              {selected !== "approve" && (
                <span className="required-label">Required</span>
              )}
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={3}
                maxLength={2000}
                required={selected !== "approve"}
                disabled={busy}
                placeholder="Explain your decision. Keep sensitive identifiers out of this note."
              />
            </label>
            <div className="confirm-decision">
              <p>
                {selected === "approve"
                  ? "Confirming authorizes vendor creation and an in-app completion notification."
                  : "The requester will see this decision and your note in the workflow."}
              </p>
              <button
                className={`button ${selected === "reject" ? "destructive" : ""}`}
                disabled={busy}
              >
                {busy
                  ? "Saving decision…"
                  : selected === "approve"
                    ? "Confirm approval"
                    : selected === "reject"
                      ? "Confirm rejection"
                      : "Confirm changes request"}
              </button>
            </div>
          </form>
        )}
        <ErrorNotice message={error} />
      </div>
    </Panel>
  );
}
