import csv
import glob
import json
import os

INPUT_DIR = "output_100k/fhir"
OUTPUT_FILE = "observations.csv"

EXCLUDED_PREFIXES = (
    "hospitalInformation",
    "practitionerInformation",
)

def coding_details(codeable):
    """Return the first available code and display."""
    codings = codeable.get("coding", []) if codeable else []

    for coding in codings:
        if coding.get("code") or coding.get("display"):
            return (
                coding.get("code", ""),
                coding.get("display", ""),
            )

    return "", (codeable or {}).get("text", "")


def extract_value(resource):
    """Extract a common FHIR value and its type."""
    for key in (
        "valueQuantity",
        "valueCodeableConcept",
        "valueString",
        "valueInteger",
        "valueDecimal",
        "valueBoolean",
        "valueDateTime",
        "valueDate",
        "valueTime",
        "valueRange",
        "valueRatio",
        "valueSampledData",
        "valuePeriod",
    ):
        if key not in resource:
            continue

        value = resource[key]

        if key == "valueQuantity":
            return value.get("value", ""), value.get("unit", ""), "Quantity"

        if key == "valueCodeableConcept":
            code, display = coding_details(value)
            return display or code, "", "CodeableConcept"

        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False), "", key

        return value, "", key.removeprefix("value").replace("value", "")

    return "", "", "NoValue"


def make_row(patient_id, obs, component=None):
    code, description = coding_details(obs.get("code", {}))

    row_code = code
    row_description = description
    value_resource = obs

    if component is not None:
        row_code, row_description = coding_details(
            component.get("code", {})
        )
        value_resource = component

    value, unit, value_type = extract_value(value_resource)

    return {
        "patient_id": patient_id,
        "observation_id": obs.get("id", ""),
        "date": (
            obs.get("effectiveDateTime")
            or obs.get("effectivePeriod", {}).get("start", "")
            or obs.get("issued", "")
        ),
        "code": row_code,
        "description": row_description,
        "component_code": (
            row_code if component is not None else ""
        ),
        "value": value,
        "unit": unit,
        "value_type": value_type,
        "status": obs.get("status", ""),
    }


rows = []

files = sorted(
    f for f in glob.glob(os.path.join(INPUT_DIR, "*.json"))
    if not os.path.basename(f).startswith(EXCLUDED_PREFIXES)
)

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
        obs = entry.get("resource", {})

        if obs.get("resourceType") != "Observation":
            continue

        components = obs.get("component", [])

        if components:
            for component in components:
                rows.append(make_row(patient_id, obs, component))
        else:
            rows.append(make_row(patient_id, obs))

fieldnames = [
    "patient_id",
    "observation_id",
    "date",
    "code",
    "description",
    "component_code",
    "value",
    "unit",
    "value_type",
    "status",
]

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Patient bundles processed: {len(files)}")
print(f"Observation rows exported: {len(rows)}")
print(f"Output file: {OUTPUT_FILE}")