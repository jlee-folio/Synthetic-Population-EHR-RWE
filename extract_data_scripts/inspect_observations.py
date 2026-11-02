import glob
import json
import os

files = [
    f for f in glob.glob("output_100k/fhir/*.json")
    if not os.path.basename(f).startswith(
        ("hospitalInformation", "practitionerInformation")
    )
]

if not files:
    raise SystemExit("No patient FHIR files found.")

filename = files[0]

with open(filename, encoding="utf-8") as f:
    bundle = json.load(f)

print("Patient bundle:", os.path.basename(filename))
print("-" * 80)

count = 0

for entry in bundle.get("entry", []):
    resource = entry.get("resource", {})

    if resource.get("resourceType") != "Observation":
        continue

    code = resource.get("code", {})
    codings = code.get("coding", [])

    label = next(
        (item.get("display") for item in codings if item.get("display")),
        code.get("text", "Unknown")
    )

    # Check common FHIR value fields.
    value = resource.get("valueQuantity")

    if value is None:
        value = resource.get("valueCodeableConcept")
    if value is None:
        value = resource.get("valueString")
    if value is None:
        value = resource.get("valueInteger")
    if value is None:
        value = resource.get("valueBoolean")

    if value is None and resource.get("component"):
        value = f"{len(resource['component'])} components"

    if value is None:
        value = "No simple value"

    date = (
        resource.get("effectiveDateTime")
        or resource.get("effectivePeriod")
        or resource.get("effectiveInstant")
        or resource.get("issued")
        or ""
    )

    print(f"Observation: {label}")
    print(f"Date:        {date}")
    print(f"Value:       {value}")
    print("-" * 80)

    count += 1

    if count >= 15:
        break

print(f"Observations displayed: {count}")
