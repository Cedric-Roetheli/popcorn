#!/usr/bin/env python3
"""
postprocess_roles.py

Usage:
    source .venv/bin/activate
    python scripts/postprocess_roles.py \
        --input "/Users/<you>/Desktop/processed_subs Kopie/prepared/master_list_with_analysis_v2.csv" \
        --output "/Users/<you>/Desktop/processed_subs Kopie/prepared/master_list_with_analysis_v2_roles.csv"
"""

import argparse
import csv
from pathlib import Path

STAGE2_COLUMNS = [
    ("Protagonist", "stage2_protagonist_name"),
    ("Antagonist", "stage2_antagonist_name"),
    ("Additional_1", "stage2_additional_1_name"),
    ("Additional_2", "stage2_additional_2_name"),
    ("Additional_3", "stage2_additional_3_name"),
]

STAGE3_ROLES = [
    ("hero", "stage3_hero_character"),
    ("villain", "stage3_villain_character"),
    ("victim", "stage3_victim_characters"),  # note: victims can be multiple names
]


def normalize(name: str) -> str:
    return name.strip().lower()


def find_role_sources(row):
    """Return a dict mapping stage3 role -> stage2 slot_name or semicolon list."""
    matches = {}
    # Prebuild lookup from normalized name to slot label
    name_to_slot = {
        normalize(row[col]): label
        for label, col in STAGE2_COLUMNS
        if row.get(col)
    }
    # Hero and villain are single names
    for role, col in STAGE3_ROLES[:2]:
        name = row.get(col, "")
        slot = name_to_slot.get(normalize(name), "")
        matches[f"stage3_{role}_source"] = slot

    # Victims may be multiple names separated by ;
    victims_raw = row.get(STAGE3_ROLES[2][1], "")
    if victims_raw:
        sources = []
        for name in victims_raw.split(";"):
            slot = name_to_slot.get(normalize(name), "")
            if slot:
                sources.append(slot)
        matches["stage3_victim_sources"] = ";".join(sources)
    else:
        matches["stage3_victim_sources"] = ""

    return matches


def main():
    parser = argparse.ArgumentParser(description="Back-fill Stage-3 hero/villain/victim to Stage-2 slots.")
    parser.add_argument("--input", type=Path, required=True, help="Existing master_list_with_analysis_v2.csv")
    parser.add_argument("--output", type=Path, required=True, help="Destination CSV with linkage columns added")
    args = parser.parse_args()

    with args.input.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Augment rows with source columns
    for row in rows:
        row.update(find_role_sources(row))

    # Ensure the new columns exist in field order
    fieldnames = reader.fieldnames or []
    for col in ["stage3_hero_source", "stage3_villain_source", "stage3_victim_sources"]:
        if col not in fieldnames:
            fieldnames.append(col)

    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
