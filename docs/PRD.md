# Source PRD

Extracted verbatim from the supplied Word document; table cells are separate paragraphs.

FlowPilot

Enterprise Workflow Automation Agent

Portfolio-grade product requirements document



1. Executive Summary

FlowPilot is an AI-powered workflow automation platform that converts unstructured business requests into structured, auditable workflows. It combines LLM-based classification and extraction with deterministic rules, tool calling, human approvals, retries, idempotency, and complete audit logs.

The product is intentionally not a chatbot. It is a system for safely performing real work with AI while keeping humans in control of sensitive actions.

2. Initial Use Case

The v1 workflow is vendor onboarding because it naturally demonstrates:

Unstructured request ingestion

Document classification and field extraction

Deterministic validation

Duplicate checks

Human approvals

External side effects through tools

Retries and failure handling

Auditability and role-based access

3. Example User Journey

A user submits: “Please onboard Acme Robotics as a new vendor. Attached are their tax form, insurance certificate, and banking information.”

Classify the request as Vendor Onboarding.

Extract company and document fields.

Validate required documentation and formats.

Check for an existing vendor.

Flag missing information or policy violations.

Route the workflow to an approver.

On approval, call the vendor-creation tool.

Send a completion notification.

Store a complete audit trail.

4. Target Users

Field

Details

Operations Team

Submits requests and tracks status.

Business Analyst

Configures workflow rules and required fields.

Reviewer / Approver

Reviews extracted data and authorizes side effects.

Software / AI Engineer

Maintains integrations, orchestration, reliability, and observability.

5. Goals

Demonstrate agent orchestration and structured tool calling.

Separate probabilistic AI reasoning from deterministic business rules.

Require human approval for sensitive side effects.

Provide a complete event-level audit trail.

Handle retries, timeouts, and idempotent execution.

Expose clean backend APIs and a usable workflow dashboard.

Show production software engineering, not just prompting.

6. Non-Goals

Building a generic Zapier competitor.

Fully autonomous execution of high-risk actions.

Allowing arbitrary user-defined code execution.

Supporting dozens of integrations in v1.

7. Workflow State Model

Field

Details

RECEIVED

Request accepted and persisted.

CLASSIFYING

Request type is inferred.

EXTRACTING

Structured fields are extracted from text/documents.

VALIDATING

Deterministic rules and duplicate checks run.

NEEDS_INFORMATION

Required information is missing or ambiguous.

PENDING_APPROVAL

Human review is required before side effects.

EXECUTING

Approved tools are running.

COMPLETED

Workflow finished successfully.

REJECTED

Approver rejected the workflow.

NEEDS_MANUAL_REVIEW

Automatic recovery failed or confidence is too low.

8. Functional Requirements

FR-1 Request Ingestion

Support manual form submission, file upload, and an API endpoint that simulates incoming email or system requests.

FR-2 Classification

Classify into vendor_onboarding, invoice_review, contract_request, or unknown. Only vendor_onboarding is fully implemented in v1.

FR-3 Structured Extraction

Extract validated fields such as company name, tax ID, contact information, document presence, and insurance expiration.

FR-4 Deterministic Validation

Rules engine checks required documents, formats, dates, completeness, and policy constraints.

FR-5 Tool Calling

Agent can call extract_document, validate_vendor, check_duplicate_vendor, create_vendor, and send_notification.

FR-6 Human Approval

Sensitive actions require explicit approval. Approvers can approve, reject, or request changes.

FR-7 Audit Trail

Every state transition, model decision, tool call, approval, retry, and failure emits an immutable audit event.

FR-8 Retry Handling

Transient failures retry with bounded attempts and backoff; exhausted retries route to NEEDS_MANUAL_REVIEW.

FR-9 Idempotency

Side-effecting tools require idempotency keys to prevent duplicate records under retries.

FR-10 Role-Based Permissions

Support requester, reviewer, approver, and admin roles.

9. Example Extracted Schema

Field

Details

company_name

Acme Robotics

tax_id

String; redacted in logs

contact_name

Primary contact

contact_email

Validated email

bank_details_present

Boolean

insurance_expiration

ISO date

10. Approval Experience

The approval page should show:

Extracted fields and confidence indicators

Deterministic validation results

Warnings and missing fields

Source documents

AI-generated summary of why the workflow is ready or blocked

Approve, Reject, and Request Changes actions

11. Audit Event Schema

Field

Details

workflow_id

Workflow identifier

event_type

STATE_CHANGED, TOOL_CALLED, APPROVAL_DECISION, ERROR, RETRY, etc.

actor

user, agent, system, approver

tool

Optional tool name

input/output

Redacted structured payload

timestamp

UTC event time

12. Reliability Requirements

Schema validation for all model outputs.

Timeouts around external tools.

Retries only for retry-safe failures.

Idempotency for every side-effecting action.

Deterministic guardrails before execution.

Human escalation for low confidence or policy failures.

Structured logging and correlation IDs across the workflow.

No sensitive data in plain-text logs.

13. Security Requirements

Validate uploaded file types and size.

Restrict tool execution to an allowlist.

Enforce role-based permissions.

Require approval before state-changing external actions.

Redact sensitive data in logs and UI where appropriate.

Persist an auditable record of every side effect.

14. Technical Architecture

Recommended architecture: Next.js frontend -> FastAPI backend -> workflow orchestrator -> LLM service + rules engine + tool layer -> Postgres. LangGraph is a good fit for orchestration if explicit state and transitions remain visible in code. A Redis-backed queue can be added for asynchronous or retryable jobs.

15. Suggested Tech Stack

Field

Details

Frontend

Next.js, React, TypeScript, Tailwind

Backend

Python, FastAPI, Pydantic

Workflow

LangGraph + explicit state model, or custom state machine

Database

Postgres

Queue

Optional Redis + Celery/RQ

Infrastructure

Docker, GitHub Actions, Render/Railway/Fly.io/AWS

16. Data Model

Field

Details

workflow

id, workflow_type, status, requester, created_at, updated_at

workflow_state

workflow_id, current_state, state_data

documents

id, workflow_id, filename, type, extracted_data

approvals

id, workflow_id, approver, decision, comments, timestamp

audit_events

id, workflow_id, event_type, actor, metadata, timestamp

17. Required UI

Dashboard: active, pending approval, failed, and completed workflows.

Request Form: submit text and attachments.

Workflow Detail: timeline of states and tool activity.

Approval Screen: structured fields, validations, warnings, sources, and decision controls.

Audit View: chronological immutable event stream.

18. Evaluation Strategy

Field

Details

Classification

Accuracy across request types

Extraction

Field-level precision/recall or exact-match accuracy

Required Fields

Recall of mandatory vendor fields

Hallucination

Unsupported extracted-field rate

Workflow Reliability

Completion rate, retry success rate, duplicate side-effect rate

Human Oversight

100% of sensitive side effects require explicit approval

19. Portfolio Success Criteria

At least 100 automated workflow scenarios.

Structured extraction benchmark with measurable accuracy.

Zero duplicate vendor creation under retry/idempotency tests.

Every state-changing action is auditable.

Every sensitive side effect requires human approval.

README includes architecture, state machine, screenshots, demo GIF, reliability design, and security considerations.

20. Milestones

Workflow state machine

Request and document ingestion

Structured extraction

Validation engine

Tool layer

Human approval workflow

Retries + idempotency

Audit logs

Dashboard and workflow UI

Tests, deployment, benchmarks, and portfolio launch

21. Portfolio Narrative

The project should communicate: “I know how to make AI systems safely perform real work.” The README should emphasize orchestration, reliability, state management, deterministic safeguards, approvals, idempotency, and auditability rather than just the LLM layer.
