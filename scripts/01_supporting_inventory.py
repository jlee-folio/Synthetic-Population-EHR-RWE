from pathlib import Path
import duckdb
import csv

# Project directories
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data_100k" / "csv"
OUT_DIR = ROOT / "outputs" / "audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)

con = duckdb.connect()

files = [
        "careplans.csv",
        "devices.csv",
        "imaging_studies.csv",
        "supplies.csv",
        "organizations.csv",
        "providers.csv",
        "payer_transitions.csv"
]

inventory = []

for filename in files:
    path = RAW_DIR / filename

    if not path.exists():
        print(f"Skipping missing file: {filename}")
        continue

    print(f"Auditing {filename}...")

    # Safely quote the file path for SQL
    escaped_path = str(path.resolve()).replace("'", "''")
    source = (
    f"read_csv_auto('{escaped_path}', "
    f"header=true, strict_mode=false, "
    f"ignore_errors=true)"
    )

    row_count = con.execute(
        f"SELECT COUNT(*) FROM {source}"
    ).fetchone()[0]

    schema = con.execute(
        f"DESCRIBE SELECT * FROM {source}"
    ).fetchall()

    for column_name, column_type, *_ in schema:
        escaped_column = '"' + column_name.replace('"', '""') + '"'

        missing_count = con.execute(
            f"SELECT COUNT(*) - COUNT({escaped_column}) "
            f"FROM {source}"
        ).fetchone()[0]

        distinct_count = con.execute(
            f"SELECT COUNT(DISTINCT {escaped_column}) "
            f"FROM {source}"
        ).fetchone()[0]

        inventory.append({
            "file_name": filename,
            "file_size_bytes": path.stat().st_size,
            "row_count": row_count,
            "column_name": column_name,
            "data_type": column_type,
            "missing_count": missing_count,
            "missing_pct": (
                round(100 * missing_count / row_count, 2)
                if row_count else None
            ),
            "distinct_count": distinct_count,
        })

# Write results without pandas
output_path = OUT_DIR / "supporting_inventory.csv"

with output_path.open(
    "w", newline="", encoding="utf-8"
) as f:
    writer = csv.DictWriter(f, fieldnames=inventory[0].keys())
    writer.writeheader()
    writer.writerows(inventory)

print(f"\nInventory saved to: {output_path}")
con.close()