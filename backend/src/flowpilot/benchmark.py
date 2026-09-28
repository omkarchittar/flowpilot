"""Extraction measurements and workflow-scenario reports with explicit provenance."""

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from flowpilot.config import Settings
from flowpilot.providers import OpenAIWorkflowProvider, ProviderError, normalize, verified_candidate

FIELDS = ["company_name", "tax_id", "contact_name", "contact_email", "insurance_expiration"]


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def same_value(field, actual, expected):
    if actual is None or expected is None:
        return actual is expected
    first, second = normalize(str(actual)).casefold(), normalize(str(expected)).casefold()
    if field == "tax_id":
        first, second = re.sub(r"[\s-]", "", first), re.sub(r"[\s-]", "", second)
    return first == second


def evaluate_case(case, provider):
    started = perf_counter()
    metadata, error = [], None
    classification, extraction, candidate = None, None, None
    try:
        result = provider.classify(case["request"])
        classification = result.value
        metadata.append(result.metadata())
        if classification.request_type == "vendor_onboarding" and classification.confidence >= 0.85:
            result = provider.extract(case["sources"])
            extraction = result.value
            metadata.append(result.metadata())
            candidate = verified_candidate(extraction, case["sources"])
    except ProviderError as exc:
        error = exc.code
    fields = {}
    if case["request_type"] == "vendor_onboarding":
        for field in FIELDS:
            expected = case["fields"][field]
            raw = getattr(extraction, field).value if extraction else None
            value = getattr(candidate, field) if candidate else None
            fields[field] = {
                "expected_present": expected is not None,
                "raw_present": raw is not None,
                "verified_present": value is not None,
                "raw_correct": extraction is not None and same_value(field, raw, expected),
                "verified_correct": candidate is not None and same_value(field, value, expected),
                "supported": candidate is not None and field in candidate.evidence,
            }
    expected_docs = set(case["documents"].items())
    actual_docs = {(d.document_id, d.kind) for d in candidate.documents} if candidate else set()
    return {
        "id": case["id"],
        "expected_type": case["request_type"],
        "predicted_type": classification.request_type if classification else None,
        "classification_correct": classification is not None
        and classification.request_type == case["request_type"],
        "classification_confidence": classification.confidence if classification else None,
        "extraction_observed": extraction is not None,
        "fields": fields,
        "documents": {
            "expected": len(expected_docs),
            "predicted": len(actual_docs),
            "correct": len(expected_docs & actual_docs),
        },
        "metadata": metadata,
        "error_code": error,
        "usage_complete": error is None,
        "latency_ms": int((perf_counter() - started) * 1000),
    }


def summarize_extraction(results):
    vendors = [r for r in results if r["expected_type"] == "vendor_onboarding"]
    fields = [field for row in vendors for field in row["fields"].values()]
    metadata = [item for row in results for item in row["metadata"]]
    correct_present = sum(
        f["expected_present"] and f["verified_present"] and f["verified_correct"] for f in fields
    )
    return {
        "cases": len(results),
        "vendor_cases": len(vendors),
        "classification_accuracy": ratio(
            sum(r["classification_correct"] for r in results), len(results)
        ),
        "classification_by_type": {
            kind: {
                "cases": sum(r["expected_type"] == kind for r in results),
                "correct": sum(
                    r["expected_type"] == kind and r["classification_correct"] for r in results
                ),
            }
            for kind in sorted({r["expected_type"] for r in results})
        },
        "extraction_coverage": ratio(sum(r["extraction_observed"] for r in vendors), len(vendors)),
        "field_metrics": {
            field: {
                "reference_values": sum(r["fields"][field]["expected_present"] for r in vendors),
                "verified_precision": ratio(
                    sum(
                        r["fields"][field]["expected_present"]
                        and r["fields"][field]["verified_present"]
                        and r["fields"][field]["verified_correct"]
                        for r in vendors
                    ),
                    sum(r["fields"][field]["verified_present"] for r in vendors),
                ),
                "required_recall": ratio(
                    sum(
                        r["fields"][field]["expected_present"]
                        and r["fields"][field]["verified_present"]
                        and r["fields"][field]["verified_correct"]
                        for r in vendors
                    ),
                    sum(r["fields"][field]["expected_present"] for r in vendors),
                ),
                "raw_exact_match": ratio(
                    sum(r["fields"][field]["raw_correct"] for r in vendors), len(vendors)
                ),
            }
            for field in FIELDS
        },
        "raw_field_exact_match": ratio(sum(f["raw_correct"] for f in fields), len(fields)),
        "verified_field_exact_match": ratio(
            sum(f["verified_correct"] for f in fields), len(fields)
        ),
        "verified_field_precision": ratio(
            correct_present, sum(f["verified_present"] for f in fields)
        ),
        "required_field_recall": ratio(correct_present, sum(f["expected_present"] for f in fields)),
        "unsupported_extracted_field_rate": ratio(
            sum(f["raw_present"] and not f["supported"] for f in fields),
            sum(f["raw_present"] for f in fields),
        ),
        "document_precision": ratio(
            sum(r["documents"]["correct"] for r in vendors),
            sum(r["documents"]["predicted"] for r in vendors),
        ),
        "document_recall": ratio(
            sum(r["documents"]["correct"] for r in vendors),
            sum(r["documents"]["expected"] for r in vendors),
        ),
        "error_rate": ratio(sum(r["error_code"] is not None for r in results), len(results)),
        "usage_coverage": ratio(sum(r["usage_complete"] for r in results), len(results)),
        "input_tokens": sum(m["input_tokens"] for m in metadata),
        "output_tokens": sum(m["output_tokens"] for m in metadata),
        "observed_models": sorted({m["model"] for m in metadata}),
    }


def read_cases(path):
    raw = Path(path).read_bytes()
    bundle = json.loads(raw)
    if bundle["schema_version"] != 1 or not bundle["cases"]:
        raise ValueError("Unsupported or empty benchmark")
    ids = set()
    for case in bundle["cases"]:
        if case["id"] in ids or case["sources"].get("request") != case["request"]:
            raise ValueError("Duplicate case or inconsistent request source")
        ids.add(case["id"])
        if case["request_type"] not in {
            "vendor_onboarding",
            "invoice_review",
            "contract_request",
            "unknown",
        }:
            raise ValueError("Unknown reference request type")
        if case["request_type"] == "vendor_onboarding" and set(case["fields"]) != set(FIELDS):
            raise ValueError(
                "Vendor reference must label all five fields, using null for absent values"
            )
        if not set(case["documents"]) <= (set(case["sources"]) - {"request"}):
            raise ValueError("Document labels must refer to uploaded evidence")
    return bundle, hashlib.sha256(raw).hexdigest()


def write_report(path, output):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(output, indent=2) + "\n")
    temporary.replace(path)


def scenario_report(junit, manifest):
    suite = ET.parse(junit).getroot()
    bundle = json.loads(Path(manifest).read_text())
    expected = {row["id"]: row for row in bundle["scenarios"]}
    required = [
        "final_state",
        "vendors",
        "sensitive_effects",
        "independently_approved_effects",
        "duplicate_side_effects",
        "audit_verified",
    ]
    rows = []
    for item in suite.iter("testcase"):
        match = re.fullmatch(r"test_workflow_scenario\[(.+)\]", item.get("name", ""))
        if not match:
            continue
        identifier = match[1]
        properties = {p.get("name"): p.get("value") for p in item.findall("./properties/property")}
        status = "passed"
        if item.find("failure") is not None or item.find("error") is not None:
            status = "failed"
        if item.find("skipped") is not None:
            status = "skipped"
        if status == "passed" and (
            identifier not in expected or any(k not in properties for k in required)
        ):
            status = "inconclusive"
        if status == "passed":
            completed = expected[identifier]["expected_state"] == "COMPLETED"
            if (
                properties["final_state"] != expected[identifier]["expected_state"]
                or properties["audit_verified"] != "True"
                or int(properties["duplicate_side_effects"]) != 0
                or int(properties["vendors"]) != int(completed)
                or int(properties["sensitive_effects"]) != 2 * int(completed)
                or properties["sensitive_effects"] != properties["independently_approved_effects"]
            ):
                status = "inconclusive"
        rows.append({"id": identifier, "status": status, "observations": properties})
    observed = Counter(row["id"] for row in rows)
    coverage_ok = set(observed) == set(expected) and all(n == 1 for n in observed.values())
    passed = coverage_ok and len(expected) >= 100 and all(row["status"] == "passed" for row in rows)
    unique = {row["id"]: row for row in rows if row["id"] in expected and observed[row["id"]] == 1}
    counts = Counter(row["status"] for row in rows)

    def values(key):
        return [
            unique.get(identifier, {}).get("observations", {}).get(key) for identifier in expected
        ]

    def total(key):
        observations = values(key)
        return (
            sum(int(v) for v in observations) if all(v is not None for v in observations) else None
        )

    effects, approved = total("sensitive_effects"), total("independently_approved_effects")
    expected_completions = sum(row["expected_state"] == "COMPLETED" for row in expected.values())
    completions = sum(
        unique.get(identifier, {}).get("observations", {}).get("final_state") == "COMPLETED"
        for identifier, spec in expected.items()
        if spec["expected_state"] == "COMPLETED"
    )
    retry_ids = [
        identifier
        for identifier, spec in expected.items()
        if spec["family"] == "retry" and spec["retryable"]
    ]
    retry_states = [
        unique.get(identifier, {}).get("observations", {}).get("final_state")
        for identifier in retry_ids
    ]
    return {
        "evidence_type": "controlled workflow contracts on PostgreSQL; not model accuracy or production reliability",
        "manifest_sha256": hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),
        "junit_sha256": hashlib.sha256(Path(junit).read_bytes()).hexdigest(),
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": passed,
        "required_scenarios": len(expected),
        "observed_scenarios": len(rows),
        "missing": sorted(set(expected) - set(observed)),
        "counts": dict(counts),
        "expected_outcome_rate": ratio(
            sum(row["status"] == "passed" for row in unique.values()), len(expected)
        ),
        "observation_coverage": {
            key: ratio(sum(v is not None for v in values(key)), len(expected)) for key in required
        },
        "approved_completion_rate": ratio(completions, expected_completions),
        "transient_retry_recovery_rate": ratio(
            sum(state == "PENDING_APPROVAL" for state in retry_states),
            len(retry_ids),
        ),
        "sensitive_effects": effects,
        "independently_approved_effects": approved,
        "approval_coverage": ratio(approved, effects)
        if approved is not None and effects is not None
        else None,
        "duplicate_vendor_creations": total("duplicate_side_effects"),
        "observed_duplicate_vendor_creations": sum(
            int(v) for v in values("duplicate_side_effects") if v is not None
        ),
        "audit_verified_scenarios": sum(v == "True" for v in values("audit_verified")),
        "scenarios": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    extraction = sub.add_parser(
        "extract", help="Measure configured provider on authored cases; incurs model usage"
    )
    extraction.add_argument("--cases", default="benchmarks/extraction.json")
    extraction.add_argument("--output", required=True)
    scenarios = sub.add_parser(
        "scenarios-report", help="Summarize completed pytest JUnit scenario evidence"
    )
    scenarios.add_argument("junit")
    scenarios.add_argument("--manifest", default="benchmarks/scenarios.json")
    scenarios.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "scenarios-report":
            output = scenario_report(args.junit, args.manifest)
            write_report(args.output, output)
            print(json.dumps({k: v for k, v in output.items() if k != "scenarios"}, indent=2))
            return 0 if output["passed"] else 1
        settings = Settings()
        provider = OpenAIWorkflowProvider(
            settings.openai_api_key.get_secret_value() if settings.openai_api_key else "",
            model=settings.generation_model,
            base_url=settings.openai_base_url,
            timeout=settings.provider_timeout_seconds,
        )
        bundle, fingerprint = read_cases(args.cases)
        output = {
            "schema_version": 1,
            "evidence_type": "observations from configured provider; endpoint authenticity is not independently verified",
            "dataset_sha256": fingerprint,
            "provider_identity": hashlib.sha256(
                settings.openai_base_url.rstrip("/").encode()
            ).hexdigest(),
            "requested_model": settings.generation_model,
            "started_at": datetime.now(UTC).isoformat(),
            "status": "running",
            "total_cases": len(bundle["cases"]),
            "results": [],
        }
        for case in bundle["cases"]:
            output["results"].append(evaluate_case(case, provider))
            output["metrics"] = summarize_extraction(output["results"])
            write_report(args.output, output)
            print(
                f"Measured {len(output['results'])}/{output['total_cases']}: {case['id']}",
                flush=True,
            )
        output.update(status="completed", completed_at=datetime.now(UTC).isoformat())
        write_report(args.output, output)
        print(json.dumps(output["metrics"], indent=2))
        return 1 if any(r["error_code"] for r in output["results"]) else 0
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError, ProviderError) as exc:
        # Never echo model content, raw fields, provider responses or credentials.
        print(
            exc.code
            if isinstance(exc, ProviderError)
            else f"Benchmark failed ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
