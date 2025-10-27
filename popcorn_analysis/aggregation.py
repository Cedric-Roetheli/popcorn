"\"\"\"Helpers to flatten stage outputs into CSV-friendly rows.\"\"\""

from __future__ import annotations

from typing import Dict, List

from .data import FilmRecord


def _label_key(label: str) -> str:
    return label.lower()


def flatten_stage1(stage1: Dict[str, str]) -> Dict[str, str]:
    if not stage1:
        return {}
    return {
        "stage1_setting": stage1.get("setting_text", ""),
        "stage1_central_conflict": stage1.get("central_conflict_text", ""),
        "stage1_evidence": stage1.get("evidence_s1", ""),
        "stage1_topic": stage1.get("topic", ""),
        "stage1_conflict_type": stage1.get("conflict_type", ""),
    }


def flatten_stage2(stage2: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    if not stage2:
        return {}
    out: Dict[str, str] = {}
    characters = stage2.get("characters", {})
    for label in ["Protagonist", "Antagonist", "Additional_1", "Additional_2", "Additional_3"]:
        data = characters.get(label, {})
        prefix = f"stage2_{_label_key(label)}"
        out[f"{prefix}_name"] = data.get("name_or_label", "")
        out[f"{prefix}_tier1"] = data.get("tier1", "")
        out[f"{prefix}_tier2"] = data.get("tier2", "")
        out[f"{prefix}_stance"] = data.get("stance", "")
        out[f"{prefix}_evidence"] = data.get("evidence", "")
        out[f"{prefix}_motive_primary"] = data.get("motive_primary", "")
        out[f"{prefix}_gender"] = data.get("gender", "")
        out[f"{prefix}_race"] = data.get("race", "")
        out[f"{prefix}_purpose_in_plot"] = data.get("purpose_in_plot", "")
    return out


def flatten_stage3(stage3: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    if not stage3:
        return {}
    hero = stage3.get("hero", {})
    villain = stage3.get("villain", {})
    victim = stage3.get("victim", {})
    return {
        "stage3_hero_character": hero.get("character", ""),
        "stage3_hero_evidence": hero.get("evidence", ""),
        "stage3_villain_character": villain.get("character", ""),
        "stage3_villain_evidence": villain.get("evidence", ""),
        "stage3_victim_characters": ";".join(victim.get("characters", [])),
        "stage3_victim_evidence": victim.get("evidence", ""),
    }


def flatten_stage4(stage4: Dict[str, Dict[str, Dict[str, float | str]]]) -> Dict[str, str]:
    if not stage4:
        return {}
    def fmt(value: float | str) -> str:
        if isinstance(value, float):
            return f"{value:.3f}"
        return value

    def pack(prefix: str, data: Dict[str, float | str]) -> Dict[str, str]:
        return {
            f"{prefix}_up_score": fmt(data.get("UP_score", "")),
            f"{prefix}_up_confidence": fmt(data.get("UP_confidence", "")),
            f"{prefix}_up_notes": fmt(data.get("UP_notes", "")),
            f"{prefix}_dc_score": fmt(data.get("DC_score", "")),
            f"{prefix}_dc_confidence": fmt(data.get("DC_confidence", "")),
            f"{prefix}_dc_notes": fmt(data.get("DC_notes", "")),
        }

    out: Dict[str, str] = {}
    out.update(pack("stage4_protagonist", stage4.get("protagonist", {})))
    out.update(pack("stage4_antagonist", stage4.get("antagonist", {})))
    film = stage4.get("film", {})
    out.update(
        {
            "stage4_film_up_score": fmt(film.get("UP_score", "")),
            "stage4_film_up_confidence": fmt(film.get("UP_confidence", "")),
            "stage4_film_up_notes": fmt(film.get("UP_notes", "")),
        }
    )
    return out


def flatten_stage5(stage5: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    if not stage5:
        return {}
    out: Dict[str, str] = {}
    groups: List[Dict[str, str]] = stage5.get("groups", [])
    for idx in (0, 1):
        prefix = f"stage5_group{idx + 1}"
        if idx < len(groups):
            data = groups[idx]
            out[f"{prefix}_label"] = data.get("label", "")
            out[f"{prefix}_type"] = data.get("type", "")
            out[f"{prefix}_relation_to_protagonist"] = data.get("relation_to_protagonist", "")
            out[f"{prefix}_portrayal"] = data.get("portrayal", "")
            out[f"{prefix}_is_threatened"] = data.get("is_threatened", "")
            out[f"{prefix}_evidence"] = data.get("evidence", "")
        else:
            out[f"{prefix}_label"] = ""
            out[f"{prefix}_type"] = ""
            out[f"{prefix}_relation_to_protagonist"] = ""
            out[f"{prefix}_portrayal"] = ""
            out[f"{prefix}_is_threatened"] = ""
            out[f"{prefix}_evidence"] = ""
    flags = stage5.get("flags", {})
    out["stage5_parochialism_flag"] = flags.get("parochialism", "")
    out["stage5_outgroup_blame_flag"] = flags.get("outgroup_blame", "")
    return out


def flatten_all(film: FilmRecord, stages: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    row: Dict[str, str] = {
        "movie_id": film.movie_id,
        "title": film.title,
        "year": str(film.year) if film.year is not None else "",
    }
    row.update(flatten_stage1(stages.get("stage1", {})))
    row.update(flatten_stage2(stages.get("stage2", {})))
    row.update(flatten_stage3(stages.get("stage3", {})))
    row.update(flatten_stage4(stages.get("stage4", {})))
    row.update(flatten_stage5(stages.get("stage5", {})))
    return row
