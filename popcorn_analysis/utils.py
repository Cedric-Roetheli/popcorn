"\"\"\"Utility helpers for the analysis pipeline.\"\"\""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class ParseError(RuntimeError):
    """Raised when stage parsing fails and a retry is required."""

    def __init__(self, stage: str, message: str):
        super().__init__(f"[{stage}] {message}")
        self.stage = stage
        self.message = message
