# run_pipeline.py
# Minimal, stage-by-stage LLM pipeline for your movie narrative project.
# Usage (example):
#   python run_pipeline.py --stage 1 --film_json data/example_film.json --out out/
#   python run_pipeline.py --stage 2 --film_json data/example_film.json --prev out/ --out out/
# Repeat for later stages, always pointing --prev at the folder that holds earlier stage outputs.

import argparse, json, hashlib, os, re, sys
from pathlib import Path
from datetime import datetime

SCHEMA_VERSION = "v0.1"
PROMPT_VERSION = {
    "stage1": "v1.0",
    "stage2": "v1.0",
    "stage3": "v1.0",
    "stage4": "v1.0",
    "stage5": "v1.0",
}

# ------------------------- ENUMS -------------------------

TOPIC = {
    "relationships_family","crime_justice","war_security","politics_governance",
    "finance_business","science_technology","disaster_crisis","supernatural_fantasy",
    "society_culture","other","not_stated"
}
CONFLICT_TYPE = {
    "violent_confrontation","pursuit_escape","survival","investigation_quest",
    "crime_heist_competition","institutional_legal_political",
    "romantic_interpersonal","deception_intrigue","other","not_stated"
}

# Stage 2 categories
HUMAN = {
    "government_official","security_military_police","corporate","criminal","terrorist",
    "scientist_engineer_expert","journalist_media","civilian_individual_or_community",
    "legal_judicial","health_medical","other_human"
}
INSTRUMENT = {
    "technology_system","financial_system_or_instrument","regulation_law_policy",
    "environment_natural_disaster","disease_pathogen","supernatural_magic","other_instrument"
}
TIER1 = {"human","instrument"}
STANCE = {"supports","opposes","mixed/neutral"}
MOTIVE = {"personal_gain","ideological","duty_service","profit","justice","survival","other","not_stated"}
GENDER = {"male","female","other_undefined"}
RACE = {"caucasian","person_of_color","other_undefined"}
PURPOSE_IN_PLOT = {"threat","constraint","tool","background","not_stated"}

# Stage 3 roles
ROLES = {"hero","villain","victim","ambiguous","none"}

# Stage 4 moral labels
UP_LABEL = {"universalist","particularist","mixed/unclear","none"}
DC_LABEL = {"deontological","consequentialist","mixed/unclear","none"}

# Stage 5 group fields
GROUP_TYPE = {"nation","local_community","family","profession","company","government_branch","movement","other"}
REL_TO_PROT = {"in_group","out_group","unclear"}
PORTRAYAL = {"positive","negative","mixed","neutral"}
YESNO_UNCLR = {"yes","no","unclear"}
FLAG_01_NONE = {"1","0","none"}

# ------------------------- UTILS -------------------------

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def require(label: str, allowed: set, field: str):
    if label not in allowed:
        raise ValueError(f"{field}: '{label}' not in allowed set: {sorted(list(allowed))}")

def require_evidence(q: str, field: str):
    if not q:
        raise ValueError(f"{field}: evidence missing")
    if len(q.split()) > 25:
        raise ValueError(f"{field}: evidence too long (>25 words)")

def read_prev(prev_dir: Path, film_id: str, stage_name: str):
    p = prev_dir / stage_name / f"{film_id}.json"
    return load_json(p) if p.exists() else None

def call_llm(prompt: str) -> str:
    """
    TODO: Replace with your model call.
    Keep deterministic settings (e.g., temperature=0) and log raw text.
    Return the raw text output as a string.
    """
    raise NotImplementedError("Implement call_llm() with your LLM provider.")

def maybe_cached(out_dir: Path, film_id: str, stage_key: str, prompt_text: str):
    cache_dir = out_dir / stage_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    h = sha(prompt_text + stage_key + PROMPT_VERSION[stage_key])
    path = cache_dir / f"{film_id}.raw.{h}.txt"
    return path

# ------------------------- PROMPTS -------------------------

STAGE1_PROMPT = """Use only the provided movie text. If unspecified, write "not stated". Answer in English.

Produce exactly these fields:
Setting: <1–2 sentences describing where/when the story primarily takes place>
Central conflict: <1–2 sentences describing the main conflict; name the protagonist(s) and who/what opposes them; state nature if clear>
Evidence: "<one ≤25-word quote or subtitle line/timecode supporting your conflict description>"
Topic: <one label from: relationships_family | crime_justice | war_security | politics_governance | finance_business | science_technology | disaster_crisis | supernatural_fantasy | society_culture | other | not_stated>
Conflict_type: <one label from: violent_confrontation | pursuit_escape | survival | investigation_quest | crime_heist_competition | institutional_legal_political | romantic_interpersonal | deception_intrigue | other | not_stated>

Movie metadata:
Title: {title}
Year: {year}

Provided text begins:
{body}
"""

STAGE2_PROMPT = """Use only the provided text. If a detail is not in the text, write "not stated". Answer in English.

Identify:
- PROTAGONIST (1)
- ANTAGONIST (1)
- ADDITIONAL IMPORTANT CHARACTERS (up to 3) relevant to the central conflict.

For each character, return exactly these fields:
name_or_label: ...
tier1: <human | instrument>
tier2: <HUMAN or INSTRUMENT label from the allowed lists below>
stance: <supports | opposes | mixed/neutral>
evidence: "<≤25-word quote or subtitle timecode>"
motive_primary: <ONLY for human; personal_gain | ideological | duty_service | profit | justice | survival | other | not_stated>
gender: <ONLY for human; male | female | other_undefined>
race: <ONLY for human; caucasian | person_of_color | other_undefined>
purpose_in_plot: <ONLY for instrument; threat | constraint | tool | background | not_stated>

Allowed tier2 values:

HUMAN: government_official | security_military_police | corporate | criminal | terrorist | scientist_engineer_expert | journalist_media | civilian_individual_or_community | legal_judicial | health_medical | other_human
INSTRUMENT: technology_system | financial_system_or_instrument | regulation_law_policy | environment_natural_disaster | disease_pathogen | supernatural_magic | other_instrument

Output exactly with these blocks (omit Additional_* blocks if unused):
Protagonist:
  name_or_label: ...
  tier1: ...
  tier2: ...
  stance: ...
  evidence: "..."
  motive_primary: ...
  gender: ...
  race: ...
  purpose_in_plot: not_stated

Antagonist:
  name_or_label: ...
  tier1: ...
  tier2: ...
  stance: ...
  evidence: "..."
  motive_primary: ...
  gender: ...
  race: ...
  purpose_in_plot: not_stated

Additional_1:
  name_or_label: ...
  tier1: ...
  tier2: ...
  stance: ...
  evidence: "..."
  motive_primary: ...
  gender: ...
  race: ...
  purpose_in_plot: ...

Additional_2:
  ...

Additional_3:
  ...

Metadata (do not change):
Title: {title}
Year: {year}
Central_conflict_from_stage1: {central_conflict}

Provided text begins:
{body}
"""

STAGE3_PROMPT = """Use only the provided text and the character list from Stage 2. Roles are optional; assign them only if clearly supported by the narrative framing. If unclear, use "none". Answer in English.

Allowed roles: hero | villain | victim | ambiguous | none
Provide a ≤25-word evidence quote for any role other than "none". For "none", briefly explain "insufficient evidence in text".

Output exactly:
Protagonist_role: <hero|villain|victim|ambiguous|none>
Protagonist_evidence: "<quote or brief reason>"

Antagonist_role: <hero|villain|victim|ambiguous|none>
Antagonist_evidence: "<quote or brief reason>"

Additional_1_role: <...>     # omit if not present
Additional_1_evidence: "<...>"

Additional_2_role: <...>     # omit if not present
Additional_2_evidence: "<...>"

Additional_3_role: <...>     # omit if not present
Additional_3_evidence: "<...>"

Metadata (do not change):
Title: {title}
Year: {year}
Central_conflict_from_stage1: {central_conflict}

Characters_from_stage2 (do not alter names; do not invent new ones):
{char_list}

Provided text begins:
{body}
"""

STAGE4_PROMPT = """Use only the provided text. Labels are optional; assign them only if clearly supported. Provide evidence quotes ≤25 words.

Definitions (brief):
Universalism: principles/rules that apply to everyone equally.
Particularism: exceptions based on relationship or group membership.
Deontological: duty/rights/rule-based reasoning.
Consequentialist: outcomes/trade-offs/"greater good" reasoning.

For each listed character, assign UP_label and rationale + evidence.
If that character’s Stage-3 role = hero, also assign DC_label and rationale + evidence.
If unclear, set label to "none" and explain briefly.

Output keys (repeat for Protagonist, Antagonist, Additional_1..3 if present):
<Character>_UP_label: <universalist | particularist | mixed/unclear | none>
<Character>_UP_rationale: <1–2 sentences>
<Character>_UP_evidence: "<≤25-word quote>"

# Heroes only:
<Character>_DC_label: <deontological | consequentialist | mixed/unclear | none>
<Character>_DC_rationale: <1–2 sentences>
<Character>_DC_evidence: "<≤25-word quote>"

Film-level moral framing:
Film_UP_label: <universalist | particularist | mixed/unclear | none>
Film_UP_rationale: <1–2 sentences>
Film_UP_evidence: "<≤25-word quote>"

Metadata:
Title: {title}
Year: {year}
Stage3_roles: {roles_summary}

Provided text begins:
{body}
"""

STAGE5_PROMPT = """Use only the provided text.

List up to two salient social groups treated as collective actors. For each group, return:
group_label: <short text>
group_type: <nation | local_community | family | profession | company | government_branch | movement | other>
relation_to_protagonist: <in_group | out_group | unclear>
portrayal: <positive | negative | mixed | neutral>
is_threatened: <yes | no | unclear>
evidence: "<≤25-word quote>"

Then set:
parochialism_flag: <1 | 0 | none>  # 1 if protagonist’s in_group is favored at others’ expense; none if unclear.
outgroup_blame_flag: <1 | 0 | none>  # 1 if an out_group is explicitly blamed; none if unclear.

Output exactly these keys. If no salient groups, return only the two flags with values "none".

Metadata:
Title: {title}
Year: {year}

Provided text begins:
{body}
"""

# ------------------------- PARSERS (simple, robust-ish) -------------------------

def parse_field(text: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", text, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""

def parse_stage1(raw: str):
    out = {
        "setting_text": parse_field(raw, "Setting"),
        "central_conflict_text": parse_field(raw, "Central conflict"),
        "evidence_s1": parse_field(raw, "Evidence").strip('"'),
        "topic": parse_field(raw, "Topic"),
        "conflict_type": parse_field(raw, "Conflict_type"),
        "prompt_version": PROMPT_VERSION["stage1"],
        "schema_version": SCHEMA_VERSION,
        "raw": raw,
    }
    # validations
    if out["topic"]: require(out["topic"], TOPIC, "Topic")
    if out["conflict_type"]: require(out["conflict_type"], CONFLICT_TYPE, "Conflict_type")
    if out["evidence_s1"]: require_evidence(out["evidence_s1"], "Evidence")
    return out

def parse_stage2(raw: str):
    # Lightweight: store raw block; downstream code can regex the blocks by header lines.
    return {"raw": raw, "prompt_version": PROMPT_VERSION["stage2"], "schema_version": SCHEMA_VERSION}

def parse_stage3(raw: str):
    return {"raw": raw, "prompt_version": PROMPT_VERSION["stage3"], "schema_version": SCHEMA_VERSION}

def parse_stage4(raw: str):
    return {"raw": raw, "prompt_version": PROMPT_VERSION["stage4"], "schema_version": SCHEMA_VERSION}

def parse_stage5(raw: str):
    return {"raw": raw, "prompt_version": PROMPT_VERSION["stage5"], "schema_version": SCHEMA_VERSION}

# ------------------------- RUNNERS -------------------------

def run_stage1(args, film):
    body = (film.get("plot","") + "\n\n" + film.get("subtitles","")).strip()
    prompt = STAGE1_PROMPT.format(title=film["title"], year=film["year"], body=body)
    cache_path = maybe_cached(Path(args.out), film["film_id"], "stage1", prompt)
    if cache_path.exists():
        raw = cache_path.read_text(encoding="utf-8")
    else:
        raw = call_llm(prompt)
        cache_path.write_text(raw, encoding="utf-8")
    parsed = parse_stage1(raw)
    save_json(Path(args.out)/"stage1"/f"{film['film_id']}.json", parsed)

def run_stage2(args, film):
    prev = read_prev(Path(args.prev), film["film_id"], "stage1")
    if not prev: raise SystemExit("Stage 1 output not found in --prev directory.")
    body = (film.get("plot","") + "\n\n" + film.get("subtitles","")).strip()
    prompt = STAGE2_PROMPT.format(
        title=film["title"], year=film["year"],
        central_conflict=prev["central_conflict_text"],
        body=body
    )
    cache_path = maybe_cached(Path(args.out), film["film_id"], "stage2", prompt)
    raw = cache_path.read_text(encoding="utf-8") if cache_path.exists() else call_llm(prompt)
    cache_path.write_text(raw, encoding="utf-8")
    parsed = parse_stage2(raw)
    save_json(Path(args.out)/"stage2"/f"{film['film_id']}.json", parsed)

def run_stage3(args, film):
    s1 = read_prev(Path(args.prev), film["film_id"], "stage1")
    s2 = read_prev(Path(args.prev), film["film_id"], "stage2")
    if not s1 or not s2: raise SystemExit("Need Stage 1 and 2 outputs in --prev.")
    body = (film.get("plot","") + "\n\n" + film.get("subtitles","")).strip()
    prompt = STAGE3_PROMPT.format(
        title=film["title"], year=film["year"],
        central_conflict=s1["central_conflict_text"],
        char_list=s2["raw"],
        body=body
    )
    cache_path = maybe_cached(Path(args.out), film["film_id"], "stage3", prompt)
    raw = cache_path.read_text(encoding="utf-8") if cache_path.exists() else call_llm(prompt)
    cache_path.write_text(raw, encoding="utf-8")
    parsed = parse_stage3(raw)
    save_json(Path(args.out)/"stage3"/f"{film['film_id']}.json", parsed)

def run_stage4(args, film):
    s3 = read_prev(Path(args.prev), film["film_id"], "stage3")
    if not s3: raise SystemExit("Need Stage 3 output in --prev.")
    body = (film.get("plot","") + "\n\n" + film.get("subtitles","")).strip()
    roles_summary = s3["raw"].splitlines()[:20]  # include a small header slice for context
    prompt = STAGE4_PROMPT.format(
        title=film["title"], year=film["year"],
        roles_summary="\n".join(roles_summary),
        body=body
    )
    cache_path = maybe_cached(Path(args.out), film["film_id"], "stage4", prompt)
    raw = cache_path.read_text(encoding="utf-8") if cache_path.exists() else call_llm(prompt)
    cache_path.write_text(raw, encoding="utf-8")
    parsed = parse_stage4(raw)
    save_json(Path(args.out)/"stage4"/f"{film['film_id']}.json", parsed)

def run_stage5(args, film):
    body = (film.get("plot","") + "\n\n" + film.get("subtitles","")).strip()
    prompt = STAGE5_PROMPT.format(title=film["title"], year=film["year"], body=body)
    cache_path = maybe_cached(Path(args.out), film["film_id"], "stage5", prompt)
    raw = cache_path.read_text(encoding="utf-8") if cache_path.exists() else call_llm(prompt)
    cache_path.write_text(raw, encoding="utf-8")
    parsed = parse_stage5(raw)
    save_json(Path(args.out)/"stage5"/f"{film['film_id']}.json", parsed)

# ------------------------- CLI -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, required=True, choices=[1,2,3,4,5])
    ap.add_argument("--film_json", type=str, required=True, help="Path to a JSON with keys: film_id, title, year, plot, subtitles(optional)")
    ap.add_argument("--prev", type=str, default=None, help="Folder containing earlier stage outputs (for stages >=2)")
    ap.add_argument("--out", type=str, required=True, help="Output folder")
    args = ap.parse_args()

    film = load_json(Path(args.film_json))
    for k in ["film_id","title","year","plot"]:
        if k not in film: raise SystemExit(f"film_json missing key: {k}")

    if args.stage == 1:
        run_stage1(args, film)
    elif args.stage == 2:
        if not args.prev: raise SystemExit("--prev is required for stage 2")
        run_stage2(args, film)
    elif args.stage == 3:
        if not args.prev: raise SystemExit("--prev is required for stage 3")
        run_stage3(args, film)
    elif args.stage == 4:
        if not args.prev: raise SystemExit("--prev is required for stage 4")
        run_stage4(args, film)
    elif args.stage == 5:
        run_stage5(args, film)

    print(f"[OK] Stage {args.stage} complete for film_id={film['film_id']} -> {args.out}")

if __name__ == "__main__":
    main()
