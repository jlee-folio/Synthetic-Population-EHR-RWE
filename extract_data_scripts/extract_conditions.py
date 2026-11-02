"""
Extract Condition resources from Synthea FHIR JSON output
and write them to conditions.csv.

Usage:
    py extract_conditions.py
    py extract_conditions.py --input output_100k/fhir --output conditions.csv
"""

import argparse
import csv
import json
from pathlib import Path


FIELDS = [
    "id",
    "patient",
    "encounter",
    "clinical_status",
    "verification_status",
    "category",
    "code",
    "description",
    "onset",
    "abatement",
    "recorded_date",
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
    """Extract a referenced resource ID, such as Patient or Encounter."""
    reference = resource.get(field, {}).get("reference", "")
    return reference.split("/", 1)[-1] if "/" in reference else reference


def extract_condition(resource):
    """Convert a FHIR Condition resource into a CSV row."""
    clinical_status = resource.get("clinicalStatus", {})
    verification_status = resource.get("verificationStatus", {})
    categories = resource.get("category", [])
    code_concept = resource.get("code", {})

    return {
        "id": resource.get("id", ""),
        "patient": get_reference(resource, "subject"),
        "encounter": get_reference(resource, "encounter"),
        "clinical_status": get_display(clinical_status),
        "verification_status": get_display(verification_status),
        "category": "; ".join(
            get_display(category) for category in categories
        ),
        "code": get_code(code_concept),
        "description": get_display(code_concept),
        "onset": (
            resource.get("onsetDateTime", "")
            or resource.get("onsetString", "")
            or resource.get("onsetPeriod", {}).get("start", "")
        ),
        "abatement": (
            resource.get("abatementDateTime", "")
            or resource.get("abatementString", "")
            or resource.get("abatementPeriod", {}).get("end", "")
        ),
        "recorded_date": resource.get("recordedDate", ""),
    }


def read_conditions(path):
    """Yield Condition resources from a FHIR JSON file."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if data.get("resourceType") == "Bundle":
        for entry in data.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Condition":
                yield resource

    elif data.get("resourceType") == "Condition":
        yield data


def main():
    parser = argparse.ArgumentParser(
        description="Extract Synthea FHIR Conditions to CSV."
    )
    parser.add_argument(
        "--input",
        default="output_100k/fhir",
        help="FHIR JSON directory (default: output_100k/fhir)",
    )
    parser.add_argument(
        "--output",
        default="conditions.csv",
        help="Output CSV file (default: conditions.csv)",
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
                for condition in read_conditions(json_file):
                    writer.writerow(extract_condition(condition))
                    count += 1
            except (json.JSONDecodeError, OSError) as error:
                print(f"Warning: skipped {json_file}: {error}")

    print(f"Extracted {count} conditions.")
    print(f"Output file: {output_file.resolve()}")


if __name__ == "__main__":
    main()