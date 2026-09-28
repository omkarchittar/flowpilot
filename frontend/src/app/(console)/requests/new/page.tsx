import { Check, ShieldCheck } from "lucide-react";
import { PageHeading } from "@/components/ui";
import { RequestForm } from "@/components/request-form";
export default function NewRequest() {
  return (
    <>
      <PageHeading
        eyebrow="Start a workflow"
        title="New vendor request"
        description="Bring the details. FlowPilot will organize the evidence and route the next step."
      />
      <div className="form-layout">
        <RequestForm />
        <aside className="form-guide">
          <span className="guide-icon">
            <ShieldCheck size={25} />
          </span>
          <h2>What happens next</h2>
          <ol>
            <li>
              <strong>Understand the request</strong>
              <p>Identify the request type and extract supported fields.</p>
            </li>
            <li>
              <strong>Check the evidence</strong>
              <p>
                Validate required documents, formats, insurance dates and
                duplicates.
              </p>
            </li>
            <li>
              <strong>Get an independent decision</strong>
              <p>
                An approver reviews the request before any vendor is created.
              </p>
            </li>
          </ol>
          <div className="guide-foot">
            <Check size={16} />
            Every step leaves an audit record.
          </div>
        </aside>
      </div>
    </>
  );
}
