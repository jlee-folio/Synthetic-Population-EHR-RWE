"""
Extract MedicationRequest resources from Synthea FHIR JSON output
and write them to medications.csv.

Usage:
    py extract_medications.py
    py extract_medications.py --input output_100k/fhir --output medications.csv
"""

import argparse
import csv
import json
from pathlib import Path


FIELDS = [
    "id",
    "patient",
    "encounter",
    "medication_code",
    "medication_description",
    "status",
    "intent",
    "authored_on",
    "start",
    "stop",
    "dosage",
    "reason_code",
    "reason_description",
    "requester",
]


def get_display(concept):
    """Return a human-readable display from a FHIR CodeableConcept."""
    if not isinstance(concept, dict):
        return ""

    for coding in concept.get("coding", []):
        if coding.get("display"):
            return coding["display"]

    return concept.get("text", "")


def get_code(concept):
    """Return the first available code from a FHIR CodeableConcept."""
    if not isinstance(concept, dict):
        return ""

    for coding in concept.get("coding", []):
        if coding.get("code"):
            return coding["code"]

    return ""


def get_reference(resource, field):
    """Extract a referenced resource ID."""
    reference = resource.get(field, {}).get("reference", "")
    return reference.split("/", 1)[-1] if "/" in reference else reference


def get_medication(resource):
    """Extract medication coding and description."""
    concept = resource.get("medicationCodeableConcept", {})

    if concept:
        return get_code(concept), get_display(concept)

    reference = resource.get("medicationReference", {})
    return "", reference.get("display", "")


def get_reasons(resource):
    """Extract medication request reason codes."""
    reasons = resource.get("reasonCode", [])
    codes = []
    descriptions = []

    for reason in reasons:
        code = get_code(reason)
        description = get_display(reason)

        if code:
            codes.append(code)
        if description:
            descriptions.append(description)

    return "; ".join(codes), "; ".join(descriptions)


def extract_medication(resource):
    """Convert a FHIR MedicationRequest into a CSV row."""
    medication_code, medication_description = get_medication(resource)
    reason_code, reason_description = get_reasons(resource)

    dosage_parts = []
    for dosage in resource.get("dosageInstruction", []):
        text = dosage.get("text", "")
        if text:
            dosage_parts.append(text)
        else:
            dose = dosage.get("doseAndRate", [])
            for item in dose:
                quantity = item.get("doseQuantity", {})
                if quantity:
                    value = quantity.get("value", "")
                    unit = quantity.get("unit", "")
                    dosage_parts.append(f"{value} {unit}".strip())

    period = resource.get("dispenseRequest", {}).get("validityPeriod", {})

    return {
        "id": resource.get("id", ""),
        "patient": get_reference(resource, "subject"),
        "encounter": get_reference(resource, "encounter"),
        "medication_code": medication_code,
        "medication_description": medication_description,
        "status": resource.get("status", ""),
        "intent": resource.get("intent", ""),
        "authored_on": resource.get("authoredOn", ""),
        "start": period.get("start", ""),
        "stop": period.get("end", ""),
        "dosage": "; ".join(dosage_parts),
        "reason_code": reason_code,
        "reason_description": reason_description,
        "requester": resource.get("requester", {}).get("display", ""),
    }


def read_medications(path):
    """Yield MedicationRequest resources from a FHIR JSON file."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if data.get("resourceType") == "Bundle":
        for entry in data.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "MedicationRequest":
                yield resource

    elif data.get("resourceType") == "MedicationRequest":
        yield data


def main():
    parser = argparse.ArgumentParser(
        description="Extract Synthea FHIR MedicationRequests to CSV."
    )
    parser.add_argument(
        "--input",
        default="output_100k/fhir",
        help="FHIR JSON directory (default: output_100k/fhir)",
    )
    parser.add_argument(
        "--output",
        default="medications.csv",
        help="Output CSV file (default: medications.csv)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_file = Path(args.output)

    if not input_dir.is_dir():
        raise SystemExit(
            f"Input directory not found: {input_dir}\n"
            "Check your Synthea output directory."
        )

    json_files = sorted(input_dir.rglob("*.json"))
    if not json_files:
        raise SystemExit(f"No JSON files found under {input_dir}")

    count = 0

    with output_file.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()

        for json_file in json_files:
            try:
                for medication in read_medications(json_file):
                    writer.writerow(extract_medication(medication))
                    count += 1
            except (json.JSONDecodeError, OSError) as error:
                print(f"Warning: skipped {json_file}: {error}")

    print(f"Extracted {count} medication requests.")
    print(f"Output file: {output_file.resolve()}")


if __name__ == "__main__":
    main()