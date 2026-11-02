import csv
import glob
import json
import os

INPUT_DIR = "output_100k/fhir"
OUTPUT_FILE = "procedures.csv"

EXCLUDED_PREFIXES = (
    "hospitalInformation",
    "practitionerInformation",
)


def coding_details(codeable):
    """Extract the first available code and display."""
    codeable = codeable or {}
    codings = codeable.get("coding", [])

    for coding in codings:
        if coding.get("code") or coding.get("display"):
            return (
                coding.get("code", ""),
                coding.get("display", ""),
            )

    return "", codeable.get("text", "")


def reference_id(reference):
    """Extract the ID portion of a FHIR reference."""
    if not reference:
        return ""

    # Example: Encounter/abc123 -> abc123
    return reference.rsplit("/", 1)[-1]


def procedure_row(patient_id, resource):
    code, description = coding_details(resource.get("code"))
    category_code, category = coding_details(
        resource.get("category")
    )

    performed = resource.get("performedPeriod", {})
    if not performed:
        performed = {}

    # FHIR versions can represent performed timing differently.
    date_start = (
        performed.get("start", "")
        or resource.get("performedDateTime", "")
        or resource.get("performedString", "")
    )

    date_end = performed.get("end", "")

    encounter = resource.get("encounter", {})
    encounter_id = reference_id(encounter.get("reference", ""))

    reasons = []
    for reason in resource.get("reasonCode", []):
        _, display = coding_details(reason)
        if display:
            reasons.append(display)

    performers = []
    for performer in resource.get("performer", []):
        actor = performer.get("actor", {})
        display = actor.get("display", "")
        ref = actor.get("reference", "")
        performers.append(display or ref)

    return {
        "patient_id": patient_id,
        "procedure_id": resource.get("id", ""),
        "encounter_id": encounter_id,
        "date_start": date_start,
        "date_end": date_end,
        "code": code,
        "description": description,
        "status": resource.get("status", ""),
        "category_code": category_code,
        "category": category,
        "reason": " | ".join(reasons),
        "performer": " | ".join(performers),
    }


files = sorted(
    filename
    for filename in glob.glob(os.path.join(INPUT_DIR, "*.json"))
    if not os.path.basename(filename).startswith(
        EXCLUDED_PREFIXES
    )
)

rows = []

for filename in files:
    with open(filename, encoding="utf-8") as f:
        bundle = json.load(f)

    patient_ids = [
        entry["resource"].get("id", "")
        for entry in bundle.get("entry", [])
        if entry.get("resource", {}).get("resourceType") == "Patient"
    ]

    patient_id = patient_ids[0] if patient_ids else ""

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})

        if resource.get("resourceType") != "Procedure":
            continue

        rows.append(procedure_row(patient_id, resource))


fieldnames = [
    "patient_id",
    "procedure_id",
    "encounter_id",
    "date_start",
    "date_end",
    "code",
    "description",
    "status",
    "category_code",
    "category",
    "reason",
    "performer",
]

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Patient bundles processed: {len(files)}")
print(f"Procedure rows exported: {len(rows)}")
print(f"Output file: {OUTPUT_FILE}")