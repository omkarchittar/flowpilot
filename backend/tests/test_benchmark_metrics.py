from copy import deepcopy

from flowpilot.benchmark import evaluate_case, summarize_extraction
from flowpilot.providers import Classification, Extraction, ModelResult

FIELDS = {
    "company_name": "Fictional Company",
    "tax_id": "91-1000000",
    "contact_name": "Jamie",
    "contact_email": "jamie@example.com",
    "insurance_expiration": "2030-12-31",
}
CASE = {
    "id": "test",
    "request_type": "vendor_onboarding",
    "request": "Please onboard the vendor",
    "sources": {"request": "Please onboard the vendor", "tax": " ".join(FIELDS.values())},
    "fields": FIELDS,
    "documents": {},
    "tags": [],
}


class Provider:
    def __init__(self, changed=False, kind="vendor_onboarding"):
        self.changed, self.kind = changed, kind

    def classify(self, text):
        return ModelResult(
            Classification(request_type=self.kind, confidence=0.99),
            "fixture",
            10,
            5,
            1,
            "classify-v1",
        )

    def extract(self, sources):
        fields = {
            k: {"value": v, "source_id": "tax", "quote": v, "confidence": 0.99}
            for k, v in FIELDS.items()
        }
        if self.changed:
            fields["tax_id"]["value"] = "92-9999999"
        return ModelResult(
            Extraction.model_validate({**fields, "documents": [], "confidence": 0.99}),
            "fixture",
            20,
            10,
            2,
            "extract-v1",
        )


def test_exact_extraction_counts_actual_observed_fields_and_usage():
    result = evaluate_case(CASE, Provider())
    summary = summarize_extraction([result])
    assert summary["classification_accuracy"] == 1
    assert summary["verified_field_precision"] == summary["required_field_recall"] == 1
    assert summary["unsupported_extracted_field_rate"] == 0
    assert summary["input_tokens"] == 30 and summary["output_tokens"] == 15


def test_filtered_hallucination_still_counts_against_recall_and_raw_support():
    summary = summarize_extraction([evaluate_case(CASE, Provider(changed=True))])
    assert summary["verified_field_precision"] == 1
    assert summary["required_field_recall"] == 0.8
    assert summary["unsupported_extracted_field_rate"] == 0.2
    assert summary["raw_field_exact_match"] == 0.8


def test_misclassification_cannot_remove_vendor_from_extraction_denominator():
    result = evaluate_case(CASE, Provider(kind="unknown"))
    summary = summarize_extraction([result])
    assert summary["classification_accuracy"] == 0
    assert summary["required_field_recall"] == 0
    assert summary["verified_field_precision"] is None
    assert summary["extraction_coverage"] == 0


def test_absent_ground_truth_field_is_not_a_correct_extracted_value():
    case = deepcopy(CASE)
    case["fields"]["tax_id"] = None
    summary = summarize_extraction([evaluate_case(case, Provider())])
    assert summary["verified_field_precision"] == 0.8
    assert summary["required_field_recall"] == 1
    assert summary["raw_field_exact_match"] == 0.8


def test_provider_failure_remains_in_all_applicable_denominators():
    from flowpilot.providers import ProviderError

    class Unavailable(Provider):
        def classify(self, text):
            raise ProviderError("provider_http_503", retryable=True)

    result = evaluate_case(CASE, Unavailable())
    summary = summarize_extraction([result])
    assert summary["classification_accuracy"] == summary["required_field_recall"] == 0
    assert summary["usage_coverage"] == 0 and summary["error_rate"] == 1


def test_authored_extraction_bundle_checksum_and_labels():
    import hashlib
    import json
    from pathlib import Path

    from flowpilot.benchmark import read_cases

    directory = Path(__file__).resolve().parents[2] / "benchmarks"
    bundle, fingerprint = read_cases(directory / "extraction.json")
    manifest = json.loads((directory / "extraction-manifest.json").read_text())
    assert fingerprint == manifest["sha256"]
    assert len(bundle["cases"]) == 32
    assert sum(case["fields"] is not None for case in bundle["cases"]) == 20
    assert {case["request_type"] for case in bundle["cases"]} == {
        "vendor_onboarding",
        "invoice_review",
        "contract_request",
        "unknown",
    }
    assert hashlib.sha256((directory / "extraction.json").read_bytes()).hexdigest() == fingerprint


def test_scenario_report_cannot_pass_missing_or_invalid_evidence(tmp_path):
    import json

    from flowpilot.benchmark import scenario_report

    manifest = tmp_path / "scenarios.json"
    manifest.write_text(
        json.dumps(
            {"scenarios": [{"id": "example", "expected_state": "COMPLETED", "family": "decision"}]}
        )
    )
    junit = tmp_path / "results.xml"
    junit.write_text(
        '<testsuites><testsuite><testcase name="test_workflow_scenario[example]"/></testsuite></testsuites>'
    )
    report = scenario_report(junit, manifest)
    assert not report["passed"] and report["counts"] == {"inconclusive": 1}
    assert report["approval_coverage"] is None
    junit.write_text("<testsuites/>")
    report = scenario_report(junit, manifest)
    assert not report["passed"] and report["missing"] == ["example"]


def test_failed_scenario_observations_are_not_dropped_from_reliability_metrics(tmp_path):
    import json
    import xml.etree.ElementTree as ET
    from pathlib import Path

    from flowpilot.benchmark import scenario_report

    manifest = Path(__file__).resolve().parents[2] / "benchmarks/scenarios.json"
    scenarios = json.loads(manifest.read_text())["scenarios"]
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite")
    for scenario in scenarios:
        item = ET.SubElement(suite, "testcase", name=f"test_workflow_scenario[{scenario['id']}]")
        completed = scenario["expected_state"] == "COMPLETED"
        values = dict(
            final_state=scenario["expected_state"],
            vendors=int(completed),
            sensitive_effects=2 * int(completed),
            independently_approved_effects=2 * int(completed),
            duplicate_side_effects=0,
            audit_verified=True,
        )
        if scenario["id"] == "execution-replay-1":
            values.update(vendors=2, sensitive_effects=3, duplicate_side_effects=1)
            ET.SubElement(item, "failure")
        if scenario["id"] == "retry-classify-1":
            values["final_state"] = "NEEDS_MANUAL_REVIEW"
            ET.SubElement(item, "failure")
        props = ET.SubElement(item, "properties")
        for key, value in values.items():
            ET.SubElement(props, "property", name=key, value=str(value))
    junit = tmp_path / "junit.xml"
    ET.ElementTree(root).write(junit)
    report = scenario_report(junit, manifest)
    assert not report["passed"]
    assert report["duplicate_vendor_creations"] == 1
    assert report["approval_coverage"] == 10 / 11
    assert report["transient_retry_recovery_rate"] == 3 / 6
    suite[0].remove(suite[0].find("properties"))
    ET.ElementTree(root).write(junit)
    incomplete = scenario_report(junit, manifest)
    assert incomplete["duplicate_vendor_creations"] is None
    assert incomplete["observed_duplicate_vendor_creations"] == 1
    assert incomplete["approval_coverage"] is None
