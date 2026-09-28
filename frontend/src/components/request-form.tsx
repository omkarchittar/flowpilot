"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  FileText,
  Info,
  Paperclip,
  UploadCloud,
  X,
} from "lucide-react";
import { useAuth } from "./auth";
import { ErrorNotice, Loading, Panel } from "./ui";
import { api, errorMessage } from "@/lib/api";
import { bytes } from "@/lib/format";
import { useResource } from "@/lib/use-resource";
import type { Workflow } from "@/lib/types";
interface Options {
  upload_limit_bytes: number;
  max_documents: number;
  accepted_extensions: string[];
}
export function RequestForm({
  workflow,
  onSaved,
}: {
  workflow?: Workflow;
  onSaved?: () => void;
}) {
  const { session } = useAuth();
  const router = useRouter();
  const options = useResource<Options>("/request-options");
  const [baseRevision] = useState(workflow?.revision);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const key = useRef<string | null>(null);
  function addFiles(selected: FileList | File[]) {
    if (!options.data) return;
    const incoming = [...files, ...Array.from(selected)];
    if (incoming.length > options.data.max_documents) {
      setError(`Attach at most ${options.data.max_documents} documents.`);
      return;
    }
    if (
      incoming.some(
        (file) =>
          !options.data!.accepted_extensions.some((ext) =>
            file.name.toLowerCase().endsWith(ext),
          ),
      )
    ) {
      setError("Choose a PDF, TXT or Markdown file.");
      return;
    }
    if (
      incoming.reduce((total, file) => total + file.size, 0) >
      options.data.upload_limit_bytes
    ) {
      setError(
        `Attachments exceed the ${bytes(options.data.upload_limit_bytes)} combined limit.`,
      );
      return;
    }
    setFiles(incoming);
    setError(undefined);
  }
  if (!options.data)
    return (
      <>
        <ErrorNotice message={options.error} retry={options.refresh} />
        {!options.error && <Loading label="Loading upload settings…" />}
      </>
    );
  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        if (busy) return;
        const body = new FormData(event.currentTarget);
        body.delete("attachments");
        for (const file of files) body.append("files", file);
        if (workflow) {
          if (workflow.revision !== baseRevision) {
            setError(
              "This request changed while you were editing. Close this form and review the latest revision before continuing.",
            );
            return;
          }
          body.set("revision", String(baseRevision));
        }
        key.current ??= crypto.randomUUID();
        setBusy(true);
        setError(undefined);
        try {
          const saved = await api<Workflow>(
            workflow ? `/workflows/${workflow.id}/revisions` : "/workflows",
            {
              method: "POST",
              body,
              headers: workflow ? {} : { "Idempotency-Key": key.current },
            },
            session!.csrf_token,
          );
          if (onSaved) onSaved();
          else router.push(`/workflows/${saved.id}`);
        } catch (cause) {
          setError(errorMessage(cause));
        } finally {
          setBusy(false);
        }
      }}
    >
      <Panel
        title={workflow ? "Update the request" : "Request details"}
        subtitle={
          workflow
            ? `Submit a complete updated description for revision ${baseRevision! + 1}.`
            : "Give the reviewer enough context to make a confident decision."
        }
      >
        <div className="form-body">
          {!workflow && (
            <label>
              Request title<span className="required-label">Required</span>
              <input
                name="title"
                required
                maxLength={200}
                placeholder="Onboard a new vendor"
                disabled={busy}
              />
            </label>
          )}
          <label>
            {workflow ? "Updated request" : "What needs to happen?"}
            <span className="required-label">Required</span>
            <textarea
              name="request_text"
              required
              minLength={10}
              maxLength={20000}
              rows={6}
              disabled={busy}
              placeholder="Describe the vendor, their contact information, and the reason for onboarding. Include any context your reviewer should know."
            />
            <span className="field-help">
              Be specific about the company and primary contact. AI-assisted
              extraction is followed by policy checks and human review.
            </span>
          </label>
        </div>
      </Panel>
      <Panel
        title="Supporting documents"
        subtitle="Tax form, insurance certificate and bank confirmation"
      >
        <div className="form-body">
          <div
            className="upload-zone"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (!busy) addFiles(e.dataTransfer.files);
            }}
          >
            <UploadCloud size={28} />
            <strong>Drop documents here, or choose files</strong>
            <p>
              PDF, TXT or Markdown · {bytes(options.data.upload_limit_bytes)}{" "}
              combined · up to {options.data.max_documents} files
            </p>
            <label className="button secondary small file-picker">
              Choose files
              <input
                type="file"
                name="attachments"
                multiple
                accept={options.data.accepted_extensions.join(",")}
                disabled={busy}
                onChange={(e) => {
                  if (e.target.files) addFiles(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
          {files.length > 0 && (
            <ul className="selected-files">
              {files.map((file, index) => (
                <li key={`${file.name}-${index}`}>
                  <FileText size={18} />
                  <div>
                    <strong>{file.name}</strong>
                    <span>{bytes(file.size)}</span>
                  </div>
                  <button
                    type="button"
                    className="icon-button"
                    disabled={busy}
                    aria-label={`Remove ${file.name}`}
                    onClick={() =>
                      setFiles((all) => all.filter((_, i) => i !== index))
                    }
                  >
                    <X size={16} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="field-help with-icon">
            <Paperclip size={15} />
            {workflow
              ? "Existing documents are retained. Upload a file with the same name to replace it in this revision."
              : "You can submit without documents. Missing evidence will be flagged for follow-up."}
          </p>
        </div>
      </Panel>
      <ErrorNotice message={error} />
      <div className="form-footer">
        <p>
          <Info size={16} />
          Submitting never authorizes vendor creation.
        </p>
        <button className="button" disabled={busy}>
          {busy
            ? "Submitting…"
            : workflow
              ? "Submit revision"
              : "Submit request"}
          <ArrowRight size={16} />
        </button>
      </div>
    </form>
  );
}
