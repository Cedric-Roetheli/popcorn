from __future__ import annotations

import json
import re
from typing import Dict, List, Tuple

from . import enums
from .prompts import PROMPT_VERSION, SCHEMA_VERSION
from .utils import ParseError


def _word_count(text: str) -> int:
    return len([w for w in text.strip().split() if w])


def _require(value: str, allowed: set, field: str, stage: str) -> None:
    if value not in allowed:
        raise ParseError(stage, f"{field}: '{value}' not in allowed set {sorted(list(allowed))}")


def _require_evidence(evidence: str, field: str, stage: str, max_words: int = 25) -> None:
    if not evidence:
        raise ParseError(stage, f"{field}: evidence missing")
    if _word_count(evidence) > max_words:
        raise ParseError(stage, f"{field}: evidence too long (>{max_words} words)")


def _parse_field(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _maybe_json(raw: str, stage: str) -> Dict[str, object] | None:
    def strip_fence(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            inner = stripped[3:]
            if inner.lower().startswith("json"):
                inner = inner.split("\n", 1)[1] if "\n" in inner else ""
            if "```" in inner:
                inner = inner.rsplit("```", 1)[0]
            stripped = inner
        return stripped.strip()

    text = strip_fence(raw)
    if not text or not text.startswith("{"):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(stage, f"Invalid JSON payload: {exc}") from exc


def _parse_key_value_map(raw: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        mapping[key.strip()] = value.strip().strip('"')
    return mapping


def _ensure_dict(raw: str, stage: str) -> Dict[str, object]:
    parsed = _maybe_json(raw, stage)
    if parsed is not None:
        if not isinstance(parsed, dict):
            raise ParseError(stage, "Expected JSON object")
        return parsed
    mapping = _parse_key_value_map(raw)
    if not mapping:
        raise ParseError(stage, "Unable to parse key/value pairs")
    return mapping


def _lookup(data: Dict[str, object], key: str, stage: str) -> object:
    if key in data:
        return data[key]
    key_norm = key.lower().replace("_", "")
    for existing_key, value in data.items():
        candidate = str(existing_key)
        if candidate == key:
            return value
        if candidate.lower() == key.lower():
            return value
        if candidate.lower().replace("_", "") == key_norm:
            return value
    available = ", ".join(str(k) for k in data.keys())
    raise ParseError(stage, f"Missing key: {key}. Available keys: {available}")


def parse_stage1(raw: str) -> Dict[str, str]:
    stage = "stage1"
    setting = _parse_field(raw, "Setting")
    conflict = _parse_field(raw, "Central conflict")
    evidence = _parse_field(raw, "Evidence").strip('"')
    topic = _parse_field(raw, "Topic")
    conflict_type = _parse_field(raw, "Conflict_type")

    if not setting or not conflict:
        raise ParseError(stage, "Setting or Central conflict missing")
    if topic:
        _require(topic, enums.TOPIC, "Topic", stage)
    if conflict_type:
        conflict_norm = conflict_type.lower().replace(" ", "_")
        conflict_map = {
            "competition": "crime_heist_competition",
            "heist": "crime_heist_competition",
            "quest": "investigation_quest",
        }
        conflict_value = conflict_map.get(conflict_norm, conflict_norm)
        _require(conflict_value, enums.CONFLICT_TYPE, "Conflict_type", stage)
        conflict_type = conflict_value
    if evidence:
        _require_evidence(evidence, "Evidence", stage, max_words=35)

    return {
        "setting_text": setting,
        "central_conflict_text": conflict,
        "evidence_s1": evidence,
        "topic": topic,
        "conflict_type": conflict_type,
        "prompt_version": PROMPT_VERSION["stage1"],
        "schema_version": SCHEMA_VERSION,
        "raw": raw,
    }


def _parse_character_block(block: str, stage: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for line in block.strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    required_common = ["name_or_label", "tier1", "tier2", "stance", "evidence"]
    for key in required_common:
        if key not in data or not data[key]:
            raise ParseError(stage, f"{key} missing in character block")

    tier1 = data["tier1"].strip().lower()
    _require(tier1, enums.TIER1, "tier1", stage)

    raw_tier2 = data.get("tier2", "").strip().lower()
    tier2_clean = raw_tier2.replace(" ", "_").replace("-", "_")

    if tier1 == "human":
        human_map = {
            "not_stated": "other_human",
            "notstated": "other_human",
            "unknown": "other_human",
            "military": "security_military_police",
            "army": "security_military_police",
        }
        tier2_value = human_map.get(tier2_clean, tier2_clean)
        _require(tier2_value, enums.HUMAN_TIER2, "tier2", stage)
        data["tier2"] = tier2_value
        motive = data.get("motive_primary", "")
        gender = data.get("gender", "")
        race = data.get("race", "")
        if not motive:
            raise ParseError(stage, "motive_primary missing for human character")
        motive_norm = motive.lower().replace("-", " ").strip()
        if motive_norm.replace(" ", "") in {"romantic", "romance", "romanticlove", "love"}:
            motive_norm = "other"
        _require(motive_norm, enums.MOTIVE, "motive_primary", stage)
        data["motive_primary"] = motive_norm
        if not gender:
            raise ParseError(stage, "gender missing for human character")
        if not race:
            raise ParseError(stage, "race missing for human character")
        gender_clean = gender.lower().strip()
        gender_norm = gender_clean.replace(" ", "").replace("-", "").replace("_", "")
        if gender_norm == "notstated":
            gender_norm = "other_undefined"
        if gender_norm in ("male", "female", "otherundefined"):
            canonical_gender = {
                "male": "male",
                "female": "female",
                "otherundefined": "other_undefined",
            }[gender_norm]
        else:
            canonical_gender = gender_norm
        _require(canonical_gender, enums.GENDER, "gender", stage)
        data["gender"] = canonical_gender

        race_clean = race.lower().strip()
        race_norm = race_clean.replace(" ", "").replace("-", "").replace("_", "")
        if race_norm == "notstated":
            race_norm = "other_undefined"
        canonical_race = {
            "caucasian": "caucasian",
            "personofcolor": "person_of_color",
            "otherundefined": "other_undefined",
        }.get(race_norm, race_norm)
        _require(canonical_race, enums.RACE, "race", stage)
        data["race"] = canonical_race
    else:
        instrument_map = {
            "not_stated": "other_instrument",
            "notstated": "other_instrument",
            "unknown": "other_instrument",
            "threat": "other_instrument",
            "obstacle": "other_instrument",
        }
        tier2_value = instrument_map.get(tier2_clean, tier2_clean)
        _require(tier2_value, enums.INSTRUMENT_TIER2, "tier2", stage)
        data["tier2"] = tier2_value
        purpose = data.get("purpose_in_plot", "")
        if not purpose:
            raise ParseError(stage, "purpose_in_plot missing for instrument")
        _require(purpose, enums.PURPOSE_IN_PLOT, "purpose_in_plot", stage)

    _require(data["stance"], enums.STANCE, "stance", stage)
    _require_evidence(data["evidence"], "evidence", stage)

    return data


def parse_stage2(raw: str) -> Dict[str, Dict[str, str]]:
    stage = "stage2"
    sections = []
    pattern = re.compile(r"^(Protagonist|Antagonist|Additional_\d+):\s*$", flags=re.MULTILINE)
    matches = list(pattern.finditer(raw))
    if not matches:
        raise ParseError(stage, "No character headers found")

    for idx, match in enumerate(matches):
        label = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else raw.find("Metadata")
        if end == -1:
            end = len(raw)
        block = raw[start:end]
        sections.append((label, _parse_character_block(block, stage)))

    characters = {label: data for label, data in sections}

    if "Protagonist" not in characters or "Antagonist" not in characters:
        raise ParseError(stage, "Protagonist or Antagonist block missing")

    return {
        "characters": characters,
        "prompt_version": PROMPT_VERSION["stage2"],
        "schema_version": SCHEMA_VERSION,
        "raw": raw,
    }


def parse_stage3(raw: str) -> Dict[str, Dict[str, str]]:
    stage = "stage3"
    data = _ensure_dict(raw, stage)

    def get(key: str) -> object:
        if key not in data:
            raise ParseError(stage, f"{key} missing")
        return data[key]

    hero_value = _lookup(data, "Hero_character", stage)
    hero_evidence = _lookup(data, "Hero_evidence", stage)
    villain_value = _lookup(data, "Villain_character", stage)
    villain_evidence = _lookup(data, "Villain_evidence", stage)
    victim_value = _lookup(data, "Victim_characters", stage)
    victim_evidence = _lookup(data, "Victim_evidence", stage)

    def normalize_name(value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    hero_name = normalize_name(hero_value)
    if hero_name.lower() == "none":
        hero_name = ""
    villain_name = normalize_name(villain_value)
    if villain_name.lower() == "none":
        villain_name = ""

    if isinstance(victim_value, list):
        victim_names = [normalize_name(item) for item in victim_value if normalize_name(item)]
    else:
        victim_str = normalize_name(victim_value)
        if victim_str.lower() == "none" or not victim_str:
            victim_names = []
        else:
            parts = re.split(r"[;,]", victim_str)
            victim_names = [normalize_name(part) for part in parts if normalize_name(part)]

    hero_evidence_text = normalize_name(hero_evidence)
    villain_evidence_text = normalize_name(villain_evidence)
    victim_evidence_text = normalize_name(victim_evidence)

    if not hero_evidence_text:
        raise ParseError(stage, "Hero_evidence missing")
    if not villain_evidence_text:
        raise ParseError(stage, "Villain_evidence missing")
    if not victim_evidence_text:
        raise ParseError(stage, "Victim_evidence missing")

    _require_evidence(hero_evidence_text, "Hero_evidence", stage)
    _require_evidence(villain_evidence_text, "Villain_evidence", stage)
    _require_evidence(victim_evidence_text, "Victim_evidence", stage)

    return {
        "hero": {"character": hero_name, "evidence": hero_evidence_text},
        "villain": {"character": villain_name, "evidence": villain_evidence_text},
        "victim": {"characters": victim_names, "evidence": victim_evidence_text},
        "prompt_version": PROMPT_VERSION["stage3"],
        "schema_version": SCHEMA_VERSION,
        "raw": raw,
    }


def _parse_float(value: object, field: str, stage: str, min_value: float, max_value: float) -> float:
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value).strip())
        except ValueError as exc:
            raise ParseError(stage, f"{field}: not a number") from exc
    if not (min_value <= number <= max_value):
        raise ParseError(stage, f"{field}: value {number} outside range [{min_value}, {max_value}]")
    return number


def parse_stage4(raw: str) -> Dict[str, Dict[str, Dict[str, float | str]]]:
    stage = "stage4"
    data = _ensure_dict(raw, stage)

    def extract(prefix: str) -> Dict[str, float | str]:
        up_score = _lookup(data, f"{prefix}_UP_score", stage)
        up_conf = _lookup(data, f"{prefix}_UP_confidence", stage)
        up_notes = _lookup(data, f"{prefix}_UP_notes", stage)
        dc_score = _lookup(data, f"{prefix}_DC_score", stage)
        dc_conf = _lookup(data, f"{prefix}_DC_confidence", stage)
        dc_notes = _lookup(data, f"{prefix}_DC_notes", stage)

        up_value = _parse_float(up_score, f"{prefix}_UP_score", stage, -1.0, 1.0)
        up_conf_value = _parse_float(up_conf, f"{prefix}_UP_confidence", stage, 0.0, 1.0)
        dc_value = _parse_float(dc_score, f"{prefix}_DC_score", stage, -1.0, 1.0)
        dc_conf_value = _parse_float(dc_conf, f"{prefix}_DC_confidence", stage, 0.0, 1.0)

        up_notes_str = str(up_notes).strip()
        dc_notes_str = str(dc_notes).strip()
        _require_evidence(up_notes_str, f"{prefix}_UP_notes", stage, max_words=35)
        _require_evidence(dc_notes_str, f"{prefix}_DC_notes", stage, max_words=35)

        return {
            "UP_score": up_value,
            "UP_confidence": up_conf_value,
            "UP_notes": up_notes_str.strip('"'),
            "DC_score": dc_value,
            "DC_confidence": dc_conf_value,
            "DC_notes": dc_notes_str.strip('"'),
        }

    def extract_film() -> Dict[str, float | str]:
        up_score = _lookup(data, "Film_UP_score", stage)
        up_conf = _lookup(data, "Film_UP_confidence", stage)
        up_notes = _lookup(data, "Film_UP_notes", stage)

        up_value = _parse_float(up_score, "Film_UP_score", stage, -1.0, 1.0)
        up_conf_value = _parse_float(up_conf, "Film_UP_confidence", stage, 0.0, 1.0)
        up_notes_str = str(up_notes).strip()
        _require_evidence(up_notes_str, "Film_UP_notes", stage, max_words=35)
        return {
            "UP_score": up_value,
            "UP_confidence": up_conf_value,
            "UP_notes": up_notes_str.strip('"'),
        }

    protagonist = extract("Protagonist")
    antagonist = extract("Antagonist")
    film = extract_film()

    return {
        "protagonist": protagonist,
        "antagonist": antagonist,
        "film": film,
        "prompt_version": PROMPT_VERSION["stage4"],
        "schema_version": SCHEMA_VERSION,
        "raw": raw,
    }


def parse_stage5(raw: str) -> Dict[str, Dict[str, str]]:
    stage = "stage5"
    data = _ensure_dict(raw, stage)
    groups: List[Dict[str, str]] = []

    def normalise(value: str) -> str:
        return value.strip().strip("\"'").lower().replace(" ", "_").replace("-", "_")

    def as_str(value: object) -> str:
        if isinstance(value, str):
            return value
        if value is None:
            return ""
        return str(value)

    for idx in (1, 2):
        try:
            label_raw = _lookup(data, f"Group_{idx}_label", stage)
        except ParseError:
            continue
        label = as_str(label_raw).strip()
        if not label or label.lower() == "none":
            continue

        group_type = as_str(_lookup(data, f"Group_{idx}_type", stage))
        relation = as_str(_lookup(data, f"Group_{idx}_relation_to_protagonist", stage))
        portrayal = as_str(_lookup(data, f"Group_{idx}_portrayal", stage))
        threatened = as_str(_lookup(data, f"Group_{idx}_is_threatened", stage))
        evidence = as_str(_lookup(data, f"Group_{idx}_evidence", stage))

        type_norm = normalise(group_type)
        relation_norm = normalise(relation)
        portrayal_norm = normalise(portrayal)
        threatened_norm = normalise(threatened)
        evidence_norm = evidence.strip()

        if type_norm == "none":
            type_norm = "other"
        if relation_norm == "none":
            relation_norm = "unclear"
        if portrayal_norm == "none":
            portrayal_norm = "neutral"
        if threatened_norm == "none":
            threatened_norm = "unclear"
        if evidence_norm.lower() == "none":
            evidence_norm = ""

        _require(type_norm, enums.GROUP_TYPE, f"Group_{idx}_type", stage)
        _require(relation_norm, enums.RELATION_TO_PROTAGONIST, f"Group_{idx}_relation_to_protagonist", stage)
        _require(portrayal_norm, enums.PORTRAYAL, f"Group_{idx}_portrayal", stage)
        _require(threatened_norm, enums.YES_NO_UNCLEAR, f"Group_{idx}_is_threatened", stage)
        if evidence_norm:
            _require_evidence(evidence_norm, f"Group_{idx}_evidence", stage)

        groups.append(
            {
                "label": label,
                "type": type_norm,
                "relation_to_protagonist": relation_norm,
                "portrayal": portrayal_norm,
                "is_threatened": threatened_norm,
                "evidence": evidence_norm,
            }
        )

    parochialism = as_str(_lookup(data, "parochialism_flag", stage))
    outgroup = as_str(_lookup(data, "outgroup_blame_flag", stage))
    parochialism_norm = normalise(parochialism)
    outgroup_norm = normalise(outgroup)
    _require(parochialism_norm, enums.FLAG_01_NONE, "parochialism_flag", stage)
    _require(outgroup_norm, enums.FLAG_01_NONE, "outgroup_blame_flag", stage)

    return {
        "groups": groups,
        "flags": {"parochialism": parochialism_norm, "outgroup_blame": outgroup_norm},
        "prompt_version": PROMPT_VERSION["stage5"],
        "schema_version": SCHEMA_VERSION,
        "raw": raw,
    }
