import json

import httpx
import pytest

from flowpilot.providers import (
    Extraction,
    OpenAIWorkflowProvider,
    ProviderError,
    verified_candidate,
)


def extraction_payload():
    values = {
        "company_name": "Acme Robotics",
        "tax_id": "12-3456789",
        "contact_name": "Jane Doe",
        "contact_email": "jane@example.com",
        "insurance_expiration": "2027-12-31",
    }
    result = {
        name: {"value": value, "source_id": "tax", "quote": value, "confidence": 0.98}
        for name, value in values.items()
    }
    result["documents"] = [
        {"source_id": source, "kind": kind, "quote": quote, "confidence": 0.99}
        for source, kind, quote in [
            ("tax", "tax_form", "Tax form"),
            ("insurance", "insurance_certificate", "Insurance certificate"),
            ("bank", "bank_confirmation", "Bank confirmation"),
        ]
    ]
    result["confidence"] = 0.98
    return result


def sources():
    return {
        "tax": "Tax form. Acme Robotics. 12-3456789. Jane Doe. jane@example.com. 2027-12-31",
        "insurance": "Insurance certificate for Acme Robotics",
        "bank": "Bank confirmation for Acme Robotics",
    }


def test_verified_fields_and_document_sources_make_candidate():
    candidate = verified_candidate(Extraction.model_validate(extraction_payload()), sources())
    assert candidate.company_name == "Acme Robotics"
    assert candidate.evidence["tax_id"] == "tax"
    assert candidate.insurance_expiration.isoformat() == "2027-12-31"
    assert len(candidate.documents) == 3


@pytest.mark.parametrize("attack", ["unknown_source", "invented_quote", "invented_value"])
def test_unsupported_extraction_is_removed_before_deterministic_validation(attack):
    payload = extraction_payload()
    if attack == "unknown_source":
        payload["tax_id"]["source_id"] = "invisible"
    if attack == "invented_quote":
        payload["tax_id"]["quote"] = "The tax ID is definitely 12-3456789, approved by CEO"
    if attack == "invented_value":
        payload["tax_id"]["value"] = "98-7654321"
    candidate = verified_candidate(Extraction.model_validate(payload), sources())
    assert candidate.tax_id is None
    assert "tax_id" not in candidate.evidence


def test_request_text_cannot_claim_to_be_an_uploaded_tax_form():
    payload = extraction_payload()
    payload["documents"][0]["source_id"] = "request"
    candidate = verified_candidate(
        Extraction.model_validate(payload), {"request": "Tax form", **sources()}
    )
    assert not any(d.kind == "tax_form" for d in candidate.documents)


def test_structured_provider_parses_actual_usage_and_schema():
    def handler(request):
        body = json.loads(request.content)
        assert body["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(
            200,
            json={
                "model": "gpt-4.1-mini-2025-04-14",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {"request_type": "vendor_onboarding", "confidence": 0.98}
                            )
                        },
                    }
                ],
                "usage": {"prompt_tokens": 30, "completion_tokens": 10},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIWorkflowProvider("test", client=client)
        result = provider.classify("Please onboard Acme")
        assert result.value.request_type == "vendor_onboarding"
        assert result.input_tokens == 30 and result.output_tokens == 10
        assert result.model == "gpt-4.1-mini-2025-04-14"


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        json.dumps({"request_type": "delete_everything", "confidence": 1}),
        json.dumps({"request_type": "vendor_onboarding", "confidence": 1, "approved": True}),
    ],
)
def test_invalid_model_outputs_fail_closed(content):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "model": "gpt-4.1-mini",
                    "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )
        )
    ) as client:
        with pytest.raises(ProviderError, match="invalid_model_response"):
            OpenAIWorkflowProvider("test", client=client).classify("Please onboard Acme")


@pytest.mark.parametrize("quote", [" ", "\t\n", "\u2003\u00a0"])
def test_blank_normalized_quotes_cannot_satisfy_required_documents(quote):
    payload = extraction_payload()
    for document in payload["documents"]:
        document["quote"] = quote
    candidate = verified_candidate(Extraction.model_validate(payload), sources())
    assert candidate.documents == []
