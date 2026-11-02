import argparse
import csv
import json
from pathlib import Path

FIELDS = [
    "id", "patient", "encounter", "clinical_status",
    "verification_status", "category", "code", "description",
    "onset", "abatement", "recorded_date",
]


def display(concept):
    if not isinstance(concept, dict):
        return ""
    for coding in concept.get("coding", []):
        if coding.get("display"):
            return coding["display"]
    return concept.get("text", "")


def code_value(concept):
    if not isinstance(concept, dict):
        return ""
    for coding in concept.get("coding", []):
        if coding.get("code"):
            return coding["code"]
    return ""


def reference(resource, field):
    value = resource.get(field) or {}
    ref = value.get("reference", "") if isinstance(value, dict) else ""
    return ref.split("/", 1)[-1] if "/" in ref else ref


def extract_condition(resource):
    onset_period = resource.get("onsetPeriod") or {}
    abatement_period = resource.get("abatementPeriod") or {}

    return {
        "id": resource.get("id", ""),
        "patient": reference(resource, "subject"),
        "encounter": reference(resource, "encounter"),
        "clinical_status": display(resource.get("clinicalStatus")),
        "verification_status": display(resource.get("verificationStatus")),
        "category": "; ".join(
            display(item) for item in resource.get("category", [])
        ),
        "code": code_value(resource.get("code")),
        "description": display(resource.get("code")),
        "onset": (
            resource.get("onsetDateTime", "")
            or resource.get("onsetString", "")
            or onset_period.get("start", "")
        ),
        "abatement": (
            resource.get("abatementDateTime", "")
            or resource.get("abatementString", "")
            or abatement_period.get("end", "")
        ),
        "recorded_date": resource.get("recordedDate", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output_100k/fhir")
    parser.add_argument(
        "--output", default="output_100k/csv/conditions_recovered.csv"
    )
    parser.add_argument(
        "--errors", default="output_100k/csv/conditions_recovery_errors.csv"
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_file = Path(args.output)
    error_file = Path(args.errors)

    if not input_dir.is_dir():
        raise SystemExit(f"Input directory not found: {input_dir}")

    if output_file.resolve() == error_file.resolve():
        raise SystemExit("Output and error log must be different files.")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    error_file.parent.mkdir(parents=True, exist_ok=True)

    json_files = sorted(input_dir.rglob("*.json"))
    condition_count = 0
    valid_files = 0
    skipped_files = 0
    empty_files = 0

    # Use exclusive creation to avoid overwriting previous recovery results.
    with output_file.open(
        "x", newline="", encoding="utf-8-sig"
    ) as out, error_file.open(
        "x", newline="", encoding="utf-8-sig"
    ) as err:
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        writer.writeheader()
        error_writer = csv.writer(err)
        error_writer.writerow(["file", "error"])

        for index, path in enumerate(json_files, start=1):
            try:
                if path.stat().st_size == 0:
                    empty_files += 1
                    skipped_files += 1
                    error_writer.writerow([str(path), "Empty file"])
                    continue

                with path.open("r", encoding="utf-8-sig") as file:
                    data = json.load(file)

                resources = []
                if data.get("resourceType") == "Bundle":
                    resources = [
                        entry.get("resource", {})
                        for entry in data.get("entry", [])
                        if isinstance(entry, dict)
                    ]
                elif data.get("resourceType") == "Condition":
                    resources = [data]

                for resource in resources:
                    if resource.get("resourceType") == "Condition":
                        writer.writerow(extract_condition(resource))
                        condition_count += 1

                valid_files += 1

            except (json.JSONDecodeError, OSError, UnicodeError) as exc:
                skipped_files += 1
                error_writer.writerow([str(path), str(exc)])

            if index % 1000 == 0:
                print(
                    f"Processed {index}/{len(json_files)} files; "
                    f"conditions extracted: {condition_count}"
                )

    print("\nRecovery finished.")
    print(f"JSON files found: {len(json_files)}")
    print(f"Files read successfully: {valid_files}")
    print(f"Files skipped: {skipped_files}")
    print(f"Empty files: {empty_files}")
    print(f"Conditions extracted: {condition_count}")
    print(f"Recovered CSV: {output_file.resolve()}")
    print(f"Error log: {error_file.resolve()}")


if __name__ == "__main__":
    main()