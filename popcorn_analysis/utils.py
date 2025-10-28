"\"\"\"Utility helpers for the analysis pipeline.\"\"\""

from __future__ import annotations

import hashlib
import ast
import json
from pathlib import Path
from typing import Any, Dict


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_json(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(text)
        if not isinstance(obj, dict):
            raise ValueError("not a JSON object")
        return obj
    except (ValueError, json.JSONDecodeError):
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError) as exc:
            raise RuntimeError(f"Failed to parse JSON for {path}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(f"Unexpected structure for {path}: {type(parsed)}")
        return parsed


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class ParseError(RuntimeError):
    """Raised when stage parsing fails and a retry is required."""

    def __init__(self, stage: str, message: str):
        super().__init__(f"[{stage}] {message}")
        self.stage = stage
        self.message = message
