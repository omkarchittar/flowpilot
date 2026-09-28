"""Pure workflow authority and deterministic vendor policy; no provider or database IO."""

import re
from datetime import date, timedelta
from enum import StrEnum

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator


class State(StrEnum):
    RECEIVED = "RECEIVED"
    CLASSIFYING = "CLASSIFYING"
    EXTRACTING = "EXTRACTING"
    VALIDATING = "VALIDATING"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"


TRANSITIONS = {
    State.RECEIVED: {State.CLASSIFYING},
    State.CLASSIFYING: {State.EXTRACTING, State.NEEDS_MANUAL_REVIEW},
    State.EXTRACTING: {State.VALIDATING, State.NEEDS_MANUAL_REVIEW},
    State.VALIDATING: {State.NEEDS_INFORMATION, State.PENDING_APPROVAL, State.NEEDS_MANUAL_REVIEW},
    State.NEEDS_INFORMATION: {State.CLASSIFYING, State.REJECTED},
    State.PENDING_APPROVAL: {
        State.EXECUTING,
        State.REJECTED,
        State.NEEDS_INFORMATION,
        State.NEEDS_MANUAL_REVIEW,
    },
    State.EXECUTING: {State.COMPLETED, State.NEEDS_MANUAL_REVIEW},
    State.NEEDS_MANUAL_REVIEW: {State.CLASSIFYING, State.REJECTED},
    State.COMPLETED: set(),
    State.REJECTED: set(),
}


def transition(current: State, target: State) -> State:
    if target not in TRANSITIONS[current]:
        raise ValueError(f"Invalid transition: {current} → {target}")
    return target


class Role(StrEnum):
    REQUESTER = "requester"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    ADMIN = "admin"


class Decision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


def authorize_decision(role: Role, decision: Decision, *, actor_id: str, requester_id: str) -> None:
    if decision == Decision.APPROVE and actor_id == requester_id:
        raise PermissionError("Cannot approve your own request")
    allowed = {Role.APPROVER, Role.ADMIN}
    if decision == Decision.REQUEST_CHANGES:
        allowed.add(Role.REVIEWER)
    if role not in allowed:
        raise PermissionError("Role cannot make this approval decision")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DocumentEvidence(StrictModel):
    document_id: str = Field(min_length=1, max_length=100)
    kind: str = Field(pattern=r"^(tax_form|insurance_certificate|bank_confirmation|other)$")
    confidence: float = Field(ge=0, le=1)


class VendorCandidate(StrictModel):
    company_name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, max_length=64)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    insurance_expiration: date | None = None
    confidence: float = Field(ge=0, le=1)
    documents: list[DocumentEvidence] = Field(default_factory=list, max_length=20)
    # This map records verified source IDs. Provider adapters must verify the
    # original quote against source content before creating this domain object.
    evidence: dict[str, str] = Field(default_factory=dict)
    field_confidences: dict[str, float] = Field(default_factory=dict)

    @field_validator("company_name", "tax_id", "contact_name", "contact_email", mode="before")
    @classmethod
    def trim(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value


class Issue(StrictModel):
    code: str
    field: str
    message: str


class ValidationReport(StrictModel):
    ready: bool
    manual_review: bool
    policy_version: str = "vendor-v1"
    issues: list[Issue]


def validate_vendor(
    candidate: VendorCandidate, *, today: date, duplicate: bool = False
) -> ValidationReport:
    issues: list[Issue] = []
    manual = False

    def issue(code: str, field: str, message: str):
        issues.append(Issue(code=code, field=field, message=message))

    required = ["company_name", "tax_id", "contact_name", "contact_email", "insurance_expiration"]
    for field in required:
        value = getattr(candidate, field)
        if value is None:
            issue("required", field, "A value is required.")
        elif not candidate.evidence.get(field):
            issue("unsupported_field", field, "Verified source evidence is required.")
    if candidate.tax_id:
        tax = candidate.tax_id
        if not re.fullmatch(r"\d{2}-?\d{7}", tax, flags=re.ASCII) or set(tax.replace("-", "")) == {
            "0"
        }:
            issue(
                "invalid_tax_id",
                "tax_id",
                "A nine-digit US employer identification number is required.",
            )
    if candidate.contact_email:
        try:
            validate_email(
                candidate.contact_email, check_deliverability=False, test_environment=True
            )
        except EmailNotValidError:
            issue("invalid_email", "contact_email", "A valid email address is required.")
    if candidate.insurance_expiration and candidate.insurance_expiration < today + timedelta(
        days=30
    ):
        issue(
            "insurance_expiring",
            "insurance_expiration",
            "Insurance must cover at least the next 30 days.",
        )
    for kind in ["tax_form", "insurance_certificate", "bank_confirmation"]:
        documents = [d for d in candidate.documents if d.kind == kind]
        if not documents:
            issue("missing_document", kind, "A supporting document is required.")
        elif not any(d.confidence >= 0.85 for d in documents):
            issue(
                "uncertain_document", kind, "Document classification requires manual verification."
            )
            manual = True
    if candidate.confidence < 0.85:
        issue(
            "low_confidence", "confidence", "Extraction confidence is below the review threshold."
        )
        manual = True
    if duplicate:
        issue("duplicate_vendor", "tax_id", "An existing vendor matches this request.")
        manual = True
    return ValidationReport(ready=not issues, manual_review=manual, issues=issues)
