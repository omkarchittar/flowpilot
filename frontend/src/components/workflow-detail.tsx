"use client";
import Link from "next/link";
import { useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  CircleAlert,
  Download,
  FileText,
  Fingerprint,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { Candidate, WorkflowDetail as Detail } from "@/lib/types";
import { useResource } from "@/lib/use-resource";
import {
  bytes,
  dateTime,
  percent,
  shortId,
  titleCase,
  workingStates,
} from "@/lib/format";
import { useAuth } from "./auth";
import { Empty, ErrorNotice, Loading, PageHeading, Panel, Status } from "./ui";
import { DecisionPanel } from "./decision-panel";
import { AuditView } from "./audit-view";
import { RequestForm } from "./request-form";
import { ReviewBriefPanel } from "./review-brief";
const fields: [
  keyof Pick<
    Candidate,
    | "company_name"
    | "tax_id"
    | "contact_name"
    | "contact_email"
    | "insurance_expiration"
  >,
  string,
][] = [
  ["company_name", "Company name"],
  ["tax_id", "Tax identifier"],
  ["contact_name", "Primary contact"],
  ["contact_email", "Contact email"],
  ["insurance_expiration", "Insurance expiration"],
];
export function WorkflowDetail({ id }: { id: string }) {
  const resource = useResource<Detail>(
    `/workflows/${encodeURIComponent(id)}`,
    3000,
  );
  const { session } = useAuth();
  const [tab, setTab] = useState("review");
  const [revising, setRevising] = useState(false);
  const workflow = resource.data;
  if (!workflow)
    return (
      <>
        <Link className="back-link" href="/workflows">
          <ArrowLeft size={16} />
          All requests
        </Link>
        <ErrorNotice message={resource.error} retry={resource.refresh} />
        {!resource.error && <Loading label="Opening the request…" />}
      </>
    );
  const candidate = workflow.candidate;
  const validation = workflow.validation;
  const processing = workingStates.includes(workflow.status);
  const canRevise =
    ["NEEDS_INFORMATION", "NEEDS_MANUAL_REVIEW"].includes(workflow.status) &&
    (session!.user.id === workflow.requester_id ||
      session!.user.role === "admin");
  return (
    <>
      <Link className="back-link" href="/workflows">
        <ArrowLeft size={16} />
        All requests
      </Link>
      <PageHeading
        eyebrow={`FP-${shortId(workflow.id)} · Revision ${workflow.revision}`}
        title={workflow.title}
        description={`Submitted ${dateTime(workflow.created_at)} · ${workflow.workflow_type ? titleCase(workflow.workflow_type) : "Awaiting classification"}`}
        action={<Status value={workflow.status} />}
      />
      <ErrorNotice message={resource.error} retry={resource.refresh} />
      <div className="workflow-tabs">
        <div role="group" aria-label="Workflow sections">
          {[
            ["review", "Review"],
            ["timeline", "Timeline"],
            ["audit", "Audit trail"],
          ].map(([value, label]) => (
            <button
              className={tab === value ? "active" : ""}
              key={value}
              aria-pressed={tab === value}
              onClick={() => setTab(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <button className="text-button" onClick={resource.refresh}>
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>
      {tab === "review" && (
        <>
          {processing && (
            <div className="notice info">
              <span className="spinner small" />
              <span>
                {workflow.status === "EXECUTING"
                  ? "Approval recorded. The worker is creating the vendor and completion notification."
                  : "FlowPilot is processing the request. This page updates automatically."}
              </span>
            </div>
          )}
          {workflow.status === "COMPLETED" && (
            <div className="notice success">
              <CheckCircle2 size={20} />
              <span>
                Vendor onboarding completed. The requester has an in-app
                notification.
              </span>
            </div>
          )}
          {workflow.status === "REJECTED" && (
            <div className="notice neutral">
              <CircleAlert size={20} />
              <span>This request was rejected. No vendor was created.</span>
            </div>
          )}
          <ReviewBriefPanel
            brief={workflow.review_brief}
            revision={workflow.revision}
            status={workflow.status}
          />
          <div className="detail-columns">
            <div className="detail-primary">
              <Panel
                title="Extracted information"
                subtitle="AI-assisted fields, checked against the supplied evidence"
                action={
                  candidate && (
                    <span className="confidence-label">
                      <Sparkles size={14} />
                      {percent(candidate.confidence)} confidence
                    </span>
                  )
                }
              >
                {candidate ? (
                  <div className="extracted-fields">
                    {fields.map(([key, label]) => {
                      const sourceId = candidate.evidence[key];
                      const source = workflow.documents.find(
                        (doc) => doc.id === sourceId,
                      );
                      return (
                        <div className="extracted-field" key={key}>
                          <div className="field-title">
                            {label}
                            {key === "tax_id" && (
                              <span className="masked-label">Masked</span>
                            )}
                          </div>
                          <div className="field-value">
                            {candidate[key] ?? (
                              <span className="missing-value">Not found</span>
                            )}
                          </div>
                          <div className="field-provenance">
                            {source ? (
                              <a href={`/api/documents/${source.id}/download`}>
                                <FileText size={12} />
                                {source.filename}
                              </a>
                            ) : sourceId === "request" ? (
                              <span>From request text</span>
                            ) : (
                              <span>No verified source</span>
                            )}
                            {candidate.field_confidences[key] !== undefined && (
                              <span className="confidence-mini">
                                <i
                                  style={{
                                    width: `${candidate.field_confidences[key] * 26}px`,
                                  }}
                                />
                                <span>
                                  {percent(candidate.field_confidences[key])}
                                </span>
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <Empty
                    title={
                      processing
                        ? "Extracting the evidence"
                        : "No extracted fields"
                    }
                    text={
                      processing
                        ? "Fields and source references will appear after classification and extraction."
                        : "The request has not produced a verified vendor candidate. Review the timeline for details."
                    }
                  />
                )}
              </Panel>
              <Panel
                title="Source documents"
                subtitle={`${workflow.documents.length} document${workflow.documents.length === 1 ? "" : "s"} attached to this revision`}
              >
                {workflow.documents.length ? (
                  <ul className="document-list">
                    {workflow.documents.map((doc) => (
                      <li key={doc.id}>
                        <span className="document-icon">
                          <FileText size={22} />
                        </span>
                        <div>
                          <strong>{doc.filename}</strong>
                          <span>
                            {doc.document_type
                              ? titleCase(doc.document_type)
                              : "Not yet classified"}{" "}
                            · {bytes(doc.size_bytes)}
                          </span>
                        </div>
                        <a
                          className="icon-button"
                          href={`/api/documents/${doc.id}/download`}
                          aria-label={`Download ${doc.filename}`}
                        >
                          <Download size={18} />
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty
                    title="No documents attached"
                    text="Tax, insurance and bank evidence are required before this request can be approved."
                  />
                )}
              </Panel>
            </div>
            <aside className="detail-secondary">
              <Panel
                title="Validation checks"
                subtitle={
                  validation
                    ? `Policy ${validation.policy_version}`
                    : "Pending deterministic checks"
                }
              >
                <div className="validation-body">
                  {validation ? (
                    <>
                      <div
                        className={`validation-headline ${validation.ready ? "is-ready" : "is-blocked"}`}
                      >
                        {validation.ready ? (
                          <ShieldCheck size={27} />
                        ) : (
                          <CircleAlert size={27} />
                        )}
                        <strong>
                          {validation.ready
                            ? "Ready for a decision"
                            : validation.manual_review
                              ? "Human review needed"
                              : "More information needed"}
                        </strong>
                        <p>
                          {validation.ready
                            ? "Required fields and documents passed checks for this revision. Policy is checked again at approval."
                            : `${validation.issues.length} check${validation.issues.length === 1 ? " needs" : "s need"} attention before this request can proceed.`}
                        </p>
                      </div>
                      {validation.issues.length ? (
                        <ul className="issue-list">
                          {validation.issues.map((issue, index) => (
                            <li key={`${issue.code}-${index}`}>
                              <CircleAlert size={16} />
                              <div>
                                <strong>{titleCase(issue.field)}</strong>
                                <p>{issue.message}</p>
                              </div>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <ul className="check-list">
                          {[
                            "Required fields supported by evidence",
                            "Tax and contact formats valid",
                            "All three document types verified",
                            "Insurance covers at least 30 days",
                            "No existing vendor match",
                          ].map((item) => (
                            <li key={item}>
                              <CheckCircle2 size={16} />
                              {item}
                            </li>
                          ))}
                        </ul>
                      )}
                    </>
                  ) : (
                    <p className="muted">
                      Checks run after a supported vendor request has been
                      classified and extracted. Review the timeline if
                      processing has stopped.
                    </p>
                  )}
                </div>
              </Panel>
              <div className="evidence-note">
                <Fingerprint size={23} />
                <div>
                  <strong>Evidence before execution</strong>
                  <p>
                    Source checks establish that values appear in the evidence.
                    Review the documents for meaning and accuracy before
                    approving.
                  </p>
                </div>
              </div>
              {workflow.model_metadata.classification && (
                <Panel title="Model activity">
                  <dl className="model-details">
                    {Object.entries(workflow.model_metadata)
                      .filter(([key]) => key !== "classification_confidence")
                      .map(
                        ([key, value]) =>
                          typeof value === "object" &&
                          value && (
                            <div key={key}>
                              <dt>{titleCase(key)}</dt>
                              <dd>
                                {value.model}
                                <span>
                                  {value.input_tokens.toLocaleString()} input ·{" "}
                                  {value.output_tokens.toLocaleString()} output
                                  tokens
                                </span>
                                <span>
                                  {value.latency_ms.toLocaleString()} ms ·{" "}
                                  {value.prompt_version}
                                </span>
                              </dd>
                            </div>
                          ),
                      )}
                  </dl>
                </Panel>
              )}
            </aside>
          </div>
          <DecisionPanel
            key={`${workflow.id}-${workflow.revision}-${workflow.status}`}
            workflow={workflow}
            onSaved={resource.refresh}
          />
          {canRevise && (
            <Panel
              title="Resolve the next step"
              subtitle="Update the request and resubmit it for fresh extraction and validation."
            >
              <div className="form-body">
                {!revising ? (
                  <button
                    className="button secondary"
                    onClick={() => setRevising(true)}
                  >
                    Revise request
                  </button>
                ) : (
                  <>
                    <button
                      className="text-button"
                      onClick={() => setRevising(false)}
                    >
                      Cancel revision
                    </button>
                    <RequestForm
                      workflow={workflow}
                      onSaved={() => {
                        setRevising(false);
                        resource.refresh();
                      }}
                    />
                  </>
                )}
              </div>
            </Panel>
          )}
          {workflow.approvals.length > 0 && (
            <Panel title="Decision history">
              <ul className="decision-history">
                {workflow.approvals.map((approval) => (
                  <li key={approval.id}>
                    <div>
                      <strong>{titleCase(approval.decision)}</strong>
                      <span>
                        Revision {approval.revision} ·{" "}
                        {dateTime(approval.created_at)}
                      </span>
                    </div>
                    {approval.comment && <p>{approval.comment}</p>}
                    <small>Recorded by user {shortId(approval.actor_id)}</small>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </>
      )}
      {tab !== "review" && (
        <AuditView workflowId={id} compact={tab === "timeline"} />
      )}
    </>
  );
}
