"\"\"\"Data loading utilities for film inputs and aggregations.\"\"\""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class FilmRecord:
    movie_id: str
    title: str
    year: Optional[int]
    summary_text: str
    subtitle_text: str
    summary_file: str
    subtitle_file: str

    def combined_text(self) -> str:
        parts = []
        if self.summary_text:
            parts.append(self.summary_text)
        if self.subtitle_text:
            parts.append(self.subtitle_text)
        return "\n\n".join(parts).strip()


def load_films_from_jsonl(path: Path) -> List[FilmRecord]:
    records: List[FilmRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            records.append(
                FilmRecord(
                    movie_id=row["movie_id"],
                    title=row["title"],
                    year=row.get("year"),
                    summary_text=row.get("summary_text", ""),
                    subtitle_text=row.get("subtitle_text", ""),
                    summary_file=row.get("summary_file", ""),
                    subtitle_file=row.get("subtitle_file", ""),
                )
            )
    return records


def load_master_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def write_master_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    if not rows:
        return
    fieldnames = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    normalized = []
    for row in rows:
        normalized.append({key: row.get(key, "") for key in fieldnames})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized)
