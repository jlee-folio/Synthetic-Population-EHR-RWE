from pathlib import Path
import csv
import duckdb

# ============================================================
# 1. Project directories
# ============================================================

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data_100k" / "csv"
OUT_DIR = ROOT / "outputs" / "audit"

OUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 2. Dataset groups
# ============================================================

GROUPS = {
    "A": {
        "name": "Core clinical",
        "files": [
            "patients_clean.csv",
            "patients.csv",
            "encounters.csv",
            "medications.csv",
            "conditions_recovered.csv",
            "conditions_from_fhir_partial.csv",
            "observations.csv",
            "procedures.csv",
            "allergies.csv",
            "immunizations.csv",
        ],
        "output": "group_A_core_clinical_inventory.csv",
    },
    "B": {
        "name": "Supporting clinical and healthcare",
        "files": [
            "careplans.csv",
            "devices.csv",
            "imaging_studies.csv",
            "supplies.csv",
            "organizations.csv",
            "providers.csv",
            "payer_transitions.csv",
        ],
        "output": "group_B_supporting_inventory.csv",
    },
    "C": {
        "name": "Claims and financial",
        "files": [
            "claims.csv",
            "claims_transactions.csv",
        ],
        "output": "group_C_claims_inventory.csv",
    },
}

# Build a filename-to-group lookup.
FILE_GROUP = {
    filename: group_id
    for group_id, group in GROUPS.items()
    for filename in group["files"]
}

INVENTORY_FIELDS = [
    "group_id",
    "group_name",
    "file_name",
    "file_size_bytes",
    "row_count",
    "column_name",
    "data_type",
    "missing_count",
    "missing_pct",
    "distinct_count",
    "audit_status",
]

SUMMARY_FIELDS = [
    "group_id",
    "group_name",
    "file_name",
    "file_size_bytes",
    "row_count",
    "column_count",
    "audit_status",
]

ISSUE_FIELDS = [
    "group_id",
    "file_name",
    "issue_type",
    "details",
]

# ============================================================
# 3. Helpers
# ============================================================

def write_csv(path, rows, fields):
    """Write a CSV with a consistent header, even if empty."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def quote_identifier(name):
    """Safely quote a DuckDB column identifier."""
    return '"' + name.replace('"', '""') + '"'


def make_source(path, tolerant=False):
    """Create a safely quoted DuckDB CSV source expression."""
    escaped_path = str(path.resolve()).replace("'", "''")

    options = [
        "header=true",
        "sample_size=-1",
    ]

    if tolerant:
        options.extend([
            "strict_mode=false",
            "ignore_errors=true",
        ])

    return (
        f"read_csv_auto('{escaped_path}', "
        f"{', '.join(options)})"
    )


def audit_file(con, path, group_id, group_name):
    """
    Attempt a strict audit first.

    If strict parsing fails, retry with tolerant parsing and
    explicitly flag the results as provisional.
    """

    file_name = path.name
    file_size = path.stat().st_size
    issues = []

    for tolerant in (False, True):
        source = make_source(path, tolerant=tolerant)

        try:
            schema = con.execute(
                f"DESCRIBE SELECT * FROM {source}"
            ).fetchall()

            if not schema:
                raise ValueError("No columns detected in CSV.")

            columns = [
                (row[0], row[1])
                for row in schema
            ]

            # Calculate all column statistics in ONE aggregate
            # query rather than scanning the file per column.
            expressions = ["COUNT(*) AS total_rows"]

            for i, (column_name, _) in enumerate(columns):
                col = quote_identifier(column_name)

                expressions.append(
                    f"COUNT(*) - COUNT({col}) AS missing_{i}"
                )

                expressions.append(
                    f"COUNT(DISTINCT {col}) AS distinct_{i}"
                )

            query = (
                f"SELECT {', '.join(expressions)} "
                f"FROM {source}"
            )

            result = con.execute(query).fetchone()

            row_count = result[0]
            inventory_rows = []

            if tolerant:
                status = "PROVISIONAL_ERRORS_SKIPPED"
            else:
                status = "OK"

            for i, (column_name, column_type) in enumerate(columns):
                missing_count = result[1 + i * 2]
                distinct_count = result[2 + i * 2]

                inventory_rows.append({
                    "group_id": group_id,
                    "group_name": group_name,
                    "file_name": file_name,
                    "file_size_bytes": file_size,
                    "row_count": row_count,
                    "column_name": column_name,
                    "data_type": column_type,
                    "missing_count": missing_count,
                    "missing_pct": (
                        round(100 * missing_count / row_count, 2)
                        if row_count else None
                    ),
                    "distinct_count": distinct_count,
                    "audit_status": status,
                })

            if tolerant:
                issues.append({
                    "group_id": group_id,
                    "file_name": file_name,
                    "issue_type": "CSV_PARSE_ERROR_TOLERANT_FALLBACK",
                    "details": (
                        "Strict parsing failed. Inventory was calculated "
                        "with ignore_errors=true; malformed records may "
                        "have been skipped. Results are provisional. "
                        "Inspect and validate the source before using "
                        "these statistics as final."
                    ),
                })

            return inventory_rows, {
                "group_id": group_id,
                "group_name": group_name,
                "file_name": file_name,
                "file_size_bytes": file_size,
                "row_count": row_count,
                "column_count": len(columns),
                "audit_status": status,
            }, issues

        except Exception as exc:
            if not tolerant:
                issues.append({
                    "group_id": group_id,
                    "file_name": file_name,
                    "issue_type": "STRICT_CSV_READ_FAILED",
                    "details": str(exc),
                })
                continue

            issues.append({
                "group_id": group_id,
                "file_name": file_name,
                "issue_type": "CSV_AUDIT_FAILED",
                "details": str(exc),
            })

    # Both strict and tolerant attempts failed.
    return [], {
        "group_id": group_id,
        "group_name": group_name,
        "file_name": file_name,
        "file_size_bytes": file_size,
        "row_count": None,
        "column_count": None,
        "audit_status": "FAILED",
    }, issues


# ============================================================
# 4. Discover files and assign groups
# ============================================================

if not RAW_DIR.exists():
    raise FileNotFoundError(
        f"Input directory does not exist: {RAW_DIR}"
    )

all_files = sorted(RAW_DIR.glob("*.csv"))

print(f"Input directory: {RAW_DIR}")
print(f"CSV files discovered: {len(all_files)}")

# Inventory every CSV, including any not yet assigned to a group.
file_groups = {}

for path in all_files:
    if path.name in FILE_GROUP:
        file_groups[path.name] = FILE_GROUP[path.name]
    else:
        file_groups[path.name] = "Unclassified"

# ============================================================
# 5. Run audit
# ============================================================

con = duckdb.connect()

all_inventory = []
all_summaries = []
all_issues = []

try:
    for path in all_files:
        group_id = file_groups[path.name]

        if group_id == "Unclassified":
            group_name = "Unclassified"
        else:
            group_name = GROUPS[group_id]["name"]

        print(f"\nAuditing [{group_id}] {path.name}...")

        inventory, summary, issues = audit_file(
            con,
            path,
            group_id,
            group_name,
        )

        all_inventory.extend(inventory)
        all_summaries.append(summary)
        all_issues.extend(issues)

        print(
            f"Status: {summary['audit_status']} | "
            f"Rows: {summary['row_count']} | "
            f"Columns: {summary['column_count']}"
        )

finally:
    con.close()

# ============================================================
# 6. Write group-specific inventories
# ============================================================

for group_id, group in GROUPS.items():
    group_rows = [
        row for row in all_inventory
        if row["group_id"] == group_id
    ]

    output_path = OUT_DIR / group["output"]

    write_csv(
        output_path,
        group_rows,
        INVENTORY_FIELDS,
    )

    print(f"\nGroup {group_id} inventory saved: {output_path}")

# ============================================================
# 7. Write combined inventory
# ============================================================

combined_path = OUT_DIR / "column_inventory_all.csv"

write_csv(
    combined_path,
    all_inventory,
    INVENTORY_FIELDS,
)

print(f"\nCombined inventory saved: {combined_path}")

# ============================================================
# 8. Write dataset-level audit summary
# ============================================================

summary_path = OUT_DIR / "audit_summary.csv"

write_csv(
    summary_path,
    all_summaries,
    SUMMARY_FIELDS,
)

print(f"Audit summary saved: {summary_path}")

# ============================================================
# 9. Write data-quality issues
# ============================================================

issues_path = OUT_DIR / "data_quality_issues.csv"

write_csv(
    issues_path,
    all_issues,
    ISSUE_FIELDS,
)

print(f"Data-quality issues saved: {issues_path}")

# ============================================================
# 10. Final report
# ============================================================

print("\n" + "=" * 60)
print("AUDIT SUMMARY")
print("=" * 60)
print(f"Files discovered: {len(all_files)}")
print(f"Files audited: {len(all_summaries)}")
print(f"Inventory rows: {len(all_inventory)}")
print(f"Issues recorded: {len(all_issues)}")

for status in ("OK", "PROVISIONAL_ERRORS_SKIPPED", "FAILED"):
    count = sum(
        row["audit_status"] == status
        for row in all_summaries
    )
    print(f"{status}: {count}")

print("\nReview data_quality_issues.csv before treating the")
print("inventory as final. Provisional results may omit records.")