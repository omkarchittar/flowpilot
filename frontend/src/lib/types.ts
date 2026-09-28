export type Role = "requester" | "reviewer" | "approver" | "admin";
export type State =
  | "RECEIVED"
  | "CLASSIFYING"
  | "EXTRACTING"
  | "VALIDATING"
  | "NEEDS_INFORMATION"
  | "PENDING_APPROVAL"
  | "EXECUTING"
  | "COMPLETED"
  | "REJECTED"
  | "NEEDS_MANUAL_REVIEW";
export type Decision = "approve" | "reject" | "request_changes";
export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  active: boolean;
  created_at: string;
}
export interface Session {
  user: User;
  csrf_token: string;
}
export interface Validation {
  ready: boolean;
  manual_review: boolean;
  policy_version: string;
  issues: { code: string; field: string; message: string }[];
}
export interface ModelCall {
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  prompt_version: string;
  prompt_fingerprint?: string;
}
export interface Workflow {
  id: string;
  title: string;
  status: State;
  workflow_type: string | null;
  requester_id: string;
  revision: number;
  created_at: string;
  updated_at: string;
  validation: Validation | null;
  model_metadata: {
    classification?: ModelCall;
    extraction?: ModelCall;
    classification_confidence?: number;
  };
}
export interface Candidate {
  company_name: string | null;
  tax_id: string | null;
  contact_name: string | null;
  contact_email: string | null;
  insurance_expiration: string | null;
  confidence: number;
  evidence: Record<string, string>;
  field_confidences: Record<string, number>;
  documents: { document_id: string; kind: string; confidence: number }[];
}
export interface Document {
  id: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  document_type: string | null;
  revision: number;
}
export interface Approval {
  id: string;
  actor_id: string;
  revision: number;
  decision: Decision;
  comment: string;
  created_at: string;
}
export interface ReviewBrief {
  status: "pending" | "complete" | "failed";
  fingerprint: string;
  context: {
    revision: number;
    source_state: State;
    assessment: "ready_for_review" | "blocked";
    issues: { id: string; message: string }[];
  };
  result?: {
    assessment: "ready_for_review" | "blocked";
    summary: string;
    issue_refs: string[];
  };
  metadata?: ModelCall;
  generated_at?: string;
  error_code?: string;
}
export interface WorkflowDetail extends Workflow {
  review_brief: ReviewBrief | null;
  candidate: Candidate | null;
  documents: Document[];
  approvals: Approval[];
}
export interface Page<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}
export interface Overview {
  counts: Partial<Record<State, number>>;
  total: number;
  pending_approval: number;
  completed: number;
  manual_review: number;
}
export interface AuditEvent {
  id: string;
  sequence: number;
  event_type: string;
  actor_id: string;
  tool: string | null;
  payload: Record<string, unknown>;
  event_hash: string;
  previous_hash: string;
  request_id: string;
  created_at: string;
}
export interface AuditPage {
  items: AuditEvent[];
  verified: boolean;
  verification_scope: "page";
  anchor_hash: string;
  has_more: boolean;
  next_cursor: number;
}
export interface Notification {
  id: string;
  workflow_id: string;
  subject: string;
  message: string;
  read_at: string | null;
  created_at: string;
}
