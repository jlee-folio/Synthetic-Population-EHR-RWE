"""
Extract Encounter resources from Synthea FHIR JSON output
and write them to encounters.csv.

Usage:
    python3 extract_encounters.py
    python3 extract_encounters.py --input output_100k/fhir
    python3 extract_encounters.py --input output_100k/fhir --output encounters.csv
"""

import argparse
import csv
import json
from pathlib import Path


FIELDS = [
    "id",
    "patient",
    "encounter_class",
    "type",
    "code",
    "description",
    "start",
    "stop",
    "reason_code",
    "reason_description",
    "service_provider",
    "status",
]


def get_display(concept):
    """Return the first available coding display or text."""
    if not isinstance(concept, dict):
        return ""

    codings = concept.get("coding", [])
    for coding in codings:
        if coding.get("display"):
            return coding["display"]

    return concept.get("text", "")


def get_code(concept):
    """Return the first available coding code."""
    if not isinstance(concept, dict):
        return ""

    for coding in concept.get("coding", []):
        if coding.get("code"):
            return coding["code"]

    return ""


def extract_encounter(resource):
    """Convert a FHIR Encounter resource to a CSV row."""
    subject = resource.get("subject", {})
    service_provider = resource.get("serviceProvider", {})
    encounter_type = (resource.get("type") or [{}])[0]
    reason = (resource.get("reasonCode") or [{}])[0]

    period = resource.get("period", {})
    encounter_class = resource.get("class", {})

    return {
        "id": resource.get("id", ""),
        "patient": subject.get("reference", "").removeprefix("Patient/"),
        "encounter_class": (
            encounter_class.get("code", "")
            if isinstance(encounter_class, dict)
            else ""
        ),
        "type": get_display(encounter_type),
        "code": get_code(encounter_type),
        "description": resource.get("text", {}).get("div", ""),
        "start": period.get("start", ""),
        "stop": period.get("end", ""),
        "reason_code": get_code(reason),
        "reason_description": get_display(reason),
        "service_provider": service_provider.get("display", ""),
        "status": resource.get("status", ""),
    }


def read_resources(path):
    """Yield Encounter resources from FHIR JSON files."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    # Synthea commonly writes a FHIR Bundle per patient.
    if data.get("resourceType") == "Bundle":
        for entry in data.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Encounter":
                yield resource

    # Also support a standalone Encounter resource.
    elif data.get("resourceType") == "Encounter":
        yield data


def main():
    parser = argparse.ArgumentParser(
        description="Extract Synthea FHIR Encounter resources to CSV."
    )
    parser.add_argument(
        "--input",
        default="output_100k/fhir",
        help="Directory containing Synthea FHIR JSON files "
             "(default: output_100k/fhir)",
    )
    parser.add_argument(
        "--output",
        default="encounters.csv",
        help="Output CSV filename (default: encounters.csv)",
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

    with output_file.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()

        for json_file in json_files:
            try:
                for encounter in read_resources(json_file):
                    writer.writerow(extract_encounter(encounter))
                    count += 1
            except (json.JSONDecodeError, OSError) as error:
                print(f"Warning: skipped {json_file}: {error}")

    print(f"Extracted {count} encounters.")
    print(f"Output file: {output_file.resolve()}")


if __name__ == "__main__":
    main()