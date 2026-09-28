from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from flowpilot.domain import (
    Decision,
    DocumentEvidence,
    Role,
    State,
    VendorCandidate,
    authorize_decision,
    transition,
    validate_vendor,
)


def candidate(**changes):
    values = dict(
        company_name="Acme Robotics",
        tax_id="12-3456789",
        contact_name="Jane Doe",
        contact_email="jane@acme.example",
        insurance_expiration=date(2027, 1, 1),
        confidence=0.98,
        documents=[
            DocumentEvidence(document_id=kind, kind=kind, confidence=0.99)
            for kind in ["tax_form", "insurance_certificate", "bank_confirmation"]
        ],
        evidence={
            key: "doc-1"
            for key in [
                "company_name",
                "tax_id",
                "contact_name",
                "contact_email",
                "insurance_expiration",
            ]
        },
    )
    values.update(changes)
    return VendorCandidate(**values)


def test_successful_state_path():
    path = [
        State.RECEIVED,
        State.CLASSIFYING,
        State.EXTRACTING,
        State.VALIDATING,
        State.PENDING_APPROVAL,
        State.EXECUTING,
        State.COMPLETED,
    ]
    for current, target in zip(path, path[1:], strict=False):
        assert transition(current, target) == target


@pytest.mark.parametrize("current", list(State))
@pytest.mark.parametrize("target", [State.RECEIVED])
def test_no_transition_can_reaccept_a_workflow(current, target):
    with pytest.raises(ValueError, match="transition"):
        transition(current, target)


@pytest.mark.parametrize("terminal", [State.COMPLETED, State.REJECTED])
@pytest.mark.parametrize("target", list(State))
def test_terminal_workflows_cannot_change(terminal, target):
    with pytest.raises(ValueError):
        transition(terminal, target)


@pytest.mark.parametrize("role", list(Role))
def test_requester_cannot_approve_own_request_even_as_admin(role):
    with pytest.raises(PermissionError, match="own"):
        authorize_decision(role, Decision.APPROVE, actor_id="one", requester_id="one")


@pytest.mark.parametrize("role", [Role.REQUESTER, Role.REVIEWER])
@pytest.mark.parametrize("decision", [Decision.APPROVE, Decision.REJECT])
def test_insufficient_role_cannot_decide(role, decision):
    with pytest.raises(PermissionError):
        authorize_decision(role, decision, actor_id="reviewer", requester_id="requester")


@pytest.mark.parametrize("role", [Role.APPROVER, Role.ADMIN])
def test_approver_can_approve_other_request(role):
    authorize_decision(role, Decision.APPROVE, actor_id="reviewer", requester_id="requester")


def test_complete_vendor_is_ready():
    result = validate_vendor(candidate(), today=date(2026, 9, 28))
    assert result.ready
    assert result.issues == []


@pytest.mark.parametrize(
    "field", ["company_name", "tax_id", "contact_name", "contact_email", "insurance_expiration"]
)
def test_missing_required_field_is_blocked(field):
    result = validate_vendor(candidate(**{field: None}), today=date(2026, 9, 28))
    assert not result.ready
    assert any(i.field == field and i.code == "required" for i in result.issues)


@pytest.mark.parametrize("tax_id", ["123", "12-34567890", "aa-bbbbbbb", "000000000", "12345678x"])
def test_invalid_tax_ids(tax_id):
    result = validate_vendor(candidate(tax_id=tax_id), today=date(2026, 9, 28))
    assert not result.ready
    assert any(i.code == "invalid_tax_id" for i in result.issues)


@pytest.mark.parametrize("offset", [-365, -1, 0, 1, 29])
def test_insurance_must_cover_policy_horizon(offset):
    today = date(2026, 9, 28)
    result = validate_vendor(
        candidate(insurance_expiration=today + timedelta(days=offset)), today=today
    )
    assert not result.ready
    assert any(i.code == "insurance_expiring" for i in result.issues)


@pytest.mark.parametrize("kind", ["tax_form", "insurance_certificate", "bank_confirmation"])
def test_missing_document(kind):
    c = candidate()
    c.documents = [doc for doc in c.documents if doc.kind != kind]
    assert any(
        i.field == kind and i.code == "missing_document"
        for i in validate_vendor(c, today=date(2026, 9, 28)).issues
    )


@pytest.mark.parametrize("confidence", [0.0, 0.1, 0.5, 0.849])
def test_low_confidence_requires_manual_review(confidence):
    result = validate_vendor(candidate(confidence=confidence), today=date(2026, 9, 28))
    assert result.manual_review
    assert not result.ready


@pytest.mark.parametrize(
    "field", ["company_name", "tax_id", "contact_name", "contact_email", "insurance_expiration"]
)
def test_field_without_source_evidence_is_not_approvable(field):
    c = candidate()
    del c.evidence[field]
    result = validate_vendor(c, today=date(2026, 9, 28))
    assert not result.ready
    assert any(i.code == "unsupported_field" and i.field == field for i in result.issues)


def test_duplicate_vendor_is_escalated():
    result = validate_vendor(candidate(), today=date(2026, 9, 28), duplicate=True)
    assert result.manual_review and not result.ready
    assert any(i.code == "duplicate_vendor" for i in result.issues)


@pytest.mark.parametrize("confidence", [-1, 1.1, float("nan"), float("inf")])
def test_model_confidence_cannot_escape_unit_interval(confidence):
    with pytest.raises(ValidationError):
        candidate(confidence=confidence)


def test_unknown_model_fields_are_rejected():
    with pytest.raises(ValidationError):
        candidate(approved=True)


def test_validation_never_includes_tax_id_in_issues():
    result = validate_vendor(candidate(tax_id="sensitive-invalid"), today=date(2026, 9, 28))
    assert "sensitive-invalid" not in result.model_dump_json()
