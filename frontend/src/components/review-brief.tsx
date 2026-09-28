import { Sparkles } from "lucide-react";
import type { ReviewBrief, State } from "@/lib/types";
import { dateTime, statusLabels, titleCase } from "@/lib/format";
import { Panel } from "./ui";

export function ReviewBriefPanel({
  brief,
  revision,
  status,
}: {
  brief: ReviewBrief | null;
  revision: number;
  status: State;
}) {
  if (!brief || brief.context.revision !== revision) return null;
  return (
    <Panel
      title="AI review brief"
      subtitle={`Recorded review facts for revision ${revision}`}
      action={
        <span className="confidence-label">
          <Sparkles size={14} />
          Advisory
        </span>
      }
    >
      <div className="review-brief-body">
        {brief.status === "pending" && (
          <p role="status">
            Preparing a review brief… Policy checks and human decisions remain
            available.
          </p>
        )}
        {brief.status === "failed" && (
          <>
            <strong>AI brief unavailable</strong>
            <p>
              Review the policy findings and source documents to continue.
              Summary generation did not complete.
            </p>
          </>
        )}
        {brief.status === "complete" && brief.result && (
          <>
            <p>{brief.result.summary}</p>
            {brief.result.issue_refs.length > 0 && (
              <div
                className="brief-references"
                aria-label="Referenced findings"
              >
                {brief.result.issue_refs.map((id) => (
                  <span key={id}>{titleCase(id.split(":")[1] ?? id)}</span>
                ))}
              </div>
            )}
            <p className="field-help">
              AI-generated wording may be imperfect. Verify the findings and
              source evidence before deciding. This brief does not authorize any
              action.
            </p>
            {brief.context.source_state !== status && (
              <p className="field-help">
                The workflow has moved on since this review snapshot. Its
                current status is {statusLabels[status].toLowerCase()}.
              </p>
            )}
            {brief.metadata && (
              <details className="brief-provenance">
                <summary>Generation details</summary>
                <p>
                  {brief.metadata.model} · {brief.metadata.input_tokens} input /{" "}
                  {brief.metadata.output_tokens} output tokens ·{" "}
                  {brief.metadata.latency_ms} ms
                </p>
                <p>
                  {brief.generated_at ? dateTime(brief.generated_at) : ""} ·{" "}
                  {brief.metadata.prompt_version}
                </p>
              </details>
            )}
          </>
        )}
      </div>
    </Panel>
  );
}
