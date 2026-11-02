import csv
import glob
import json
import os
from collections import Counter

input_dir = "output/fhir"
output_file = "patient_summary.csv"

excluded_prefixes = (
    "hospitalInformation",
    "practitionerInformation",
)

summary_rows = []

for filename in glob.glob(os.path.join(input_dir, "*.json")):
    if os.path.basename(filename).startswith(excluded_prefixes):
        continue

    with open(filename, encoding="utf-8") as f:
        bundle = json.load(f)

    resources = [
        entry["resource"]
        for entry in bundle.get("entry", [])
        if isinstance(entry, dict)
        and isinstance(entry.get("resource"), dict)
    ]

    patients = [
        r for r in resources
        if r.get("resourceType") == "Patient"
    ]

    if len(patients) != 1:
        print(
            f"WARNING: {filename} contains "
            f"{len(patients)} Patient resources"
        )
        continue

    patient = patients[0]
    counts = Counter(
        r.get("resourceType", "UNKNOWN")
        for r in resources
    )

    names = patient.get("name", [])
    name = names[0] if names else {}

    given = " ".join(name.get("given", []))
    family = name.get("family", "")
    full_name = " ".join(
        part for part in [given, family] if part
    )

    summary_rows.append({
        "patient_id": patient.get("id", ""),
        "name": full_name,
        "birth_date": patient.get("birthDate", ""),
        "gender": patient.get("gender", ""),
        "encounters": counts["Encounter"],
        "conditions": counts["Condition"],
        "observations": counts["Observation"],
        "procedures": counts["Procedure"],
        "medication_requests": counts["MedicationRequest"],
        "allergies": counts["AllergyIntolerance"],
    })

fieldnames = [
    "patient_id",
    "name",
    "birth_date",
    "gender",
    "encounters",
    "conditions",
    "observations",
    "procedures",
    "medication_requests",
    "allergies",
]

with open(output_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(summary_rows)

print(f"Patients summarized: {len(summary_rows)}")
print(f"CSV created: {output_file}")