import csv
import glob
import json
import os

INPUT_DIR = "output_100k/fhir"
OUTPUT_FILE = "patients.csv"

EXCLUDED_PREFIXES = (
    "hospitalInformation",
    "practitionerInformation",
)


def get_name(patient):
    """Extract the first available official or usual name."""
    names = patient.get("name", [])

    if not names:
        return "", "", ""

    name = next(
        (
            item for item in names
            if item.get("use") in ("official", "usual")
        ),
        names[0],
    )

    given = " ".join(name.get("given", []))
    family = name.get("family", "")

    full_name = " ".join(
        part for part in [given, family] if part
    )

    return given, family, full_name


def get_address(patient):
    """Extract the first available address."""
    addresses = patient.get("address", [])

    if not addresses:
        return {
            "city": "",
            "state": "",
            "postal_code": "",
            "country": "",
        }

    address = next(
        (
            item for item in addresses
            if item.get("use") == "home"
        ),
        addresses[0],
    )

    return {
        "city": address.get("city", ""),
        "state": address.get("state", ""),
        "postal_code": address.get("postalCode", ""),
        "country": address.get("country", ""),
    }


files = sorted(
    filename
    for filename in glob.glob(
        os.path.join(INPUT_DIR, "*.json")
    )
    if not os.path.basename(filename).startswith(
        EXCLUDED_PREFIXES
    )
)

rows = []
seen_patient_ids = set()

for filename in files:
    with open(filename, encoding="utf-8") as f:
        bundle = json.load(f)

    for entry in bundle.get("entry", []):
        patient = entry.get("resource", {})

        if patient.get("resourceType") != "Patient":
            continue

        patient_id = patient.get("id", "")

        if not patient_id:
            print(f"WARNING: Patient without ID in {filename}")
            continue

        if patient_id in seen_patient_ids:
            print(f"WARNING: Duplicate patient ID: {patient_id}")
            continue

        seen_patient_ids.add(patient_id)

        first_name, last_name, full_name = get_name(patient)
        address = get_address(patient)

        marital_code = patient.get("maritalStatus", {})
        marital_codings = marital_code.get("coding", [])

        marital_status = next(
            (
                item.get("display", item.get("code", ""))
                for item in marital_codings
                if item.get("display") or item.get("code")
            ),
            marital_code.get("text", ""),
        )

        rows.append({
            "patient_id": patient_id,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "birth_date": patient.get("birthDate", ""),
            "gender": patient.get("gender", ""),
            "marital_status": marital_status,
            "city": address["city"],
            "state": address["state"],
            "postal_code": address["postal_code"],
            "country": address["country"],
            "deceased": patient.get("deceasedBoolean", ""),
            "multiple_birth": patient.get("multipleBirthBoolean", ""),
        })


fieldnames = [
    "patient_id",
    "first_name",
    "last_name",
    "full_name",
    "birth_date",
    "gender",
    "marital_status",
    "city",
    "state",
    "postal_code",
    "country",
    "deceased",
    "multiple_birth",
]

with open(
    OUTPUT_FILE,
    "w",
    newline="",
    encoding="utf-8-sig",
) as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"FHIR files processed: {len(files)}")
print(f"Unique patients exported: {len(rows)}")
print(f"Output file: {OUTPUT_FILE}")