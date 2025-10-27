"\"\"\"Prompt templates for each analysis stage.\"\"\""

from __future__ import annotations

SCHEMA_VERSION = "v0.2"
PROMPT_VERSION = {
    "stage1": "v1.1",
    "stage2": "v1.0",
    "stage3": "v2.0",
    "stage4": "v2.0",
    "stage5": "v1.0",
}

STAGE1_PROMPT = """Use only the provided movie text. If unspecified, write "not stated". Answer in English.

Produce exactly these fields:
Setting: <1–2 sentences describing where/when the story primarily takes place>
Central conflict: <1–2 sentences describing the main conflict; name the protagonist(s) and who/what opposes them; state nature if clear>
Evidence: "<one ≤35-word quote or subtitle line/timecode supporting your conflict description>"
Topic: <one label from: relationships_family | crime_justice | war_security | politics_governance | finance_business | science_technology | disaster_crisis | supernatural_fantasy | society_culture | other | not_stated>
Conflict_type: <one label from: violent_confrontation | pursuit_escape | survival | investigation_quest | crime_heist_competition | institutional_legal_political | romantic_interpersonal | deception_intrigue | other | not_stated>

Movie metadata:
Title: {title}
Year: {year}

Provided text begins:
{body}
"""

STAGE2_PROMPT = """Use only the provided movie text. If unspecified, write "not stated". Answer in English.

Identify the following, focusing on the central conflict:
- PROTAGONIST (1)
- ANTAGONIST (1)
- ADDITIONAL IMPORTANT CHARACTERS (up to 3) relevant to the conflict.

For each character, return the fields exactly as shown. Provide one ≤25-word quote or subtitle timecode as evidence.
Allowed tier1: human | instrument
If tier1 = human, pick tier2 from: government_official | security_military_police | corporate | criminal | terrorist | scientist_engineer_expert | journalist_media | civilian_individual_or_community | legal_judicial | health_medical | other_human
If tier1 = instrument, pick tier2 from: technology_system | financial_system_or_instrument | regulation_law_policy | environment_natural_disaster | disease_pathogen | supernatural_magic | other_instrument

All characters:
  stance: supports | opposes | mixed/neutral
  evidence: "<≤25-word quote or subtitle timecode>"
Human only:
  motive_primary: personal_gain | ideological | duty_service | profit | justice | survival | other | not_stated
  gender: male | female | other_undefined
  race: caucasian | person_of_color | other_undefined
Instrument only:
  purpose_in_plot: threat | constraint | tool | background | not_stated

Output exactly with these blocks (omit Additional_* if unused):

Protagonist:
  name_or_label: ...
  tier1: ...
  tier2: ...
  stance: ...
  evidence: "..."
  motive_primary: ...
  gender: ...
  race: ...
  purpose_in_plot: ...

Antagonist:
  name_or_label: ...
  tier1: ...
  tier2: ...
  stance: ...
  evidence: "..."
  motive_primary: ...
  gender: ...
  race: ...
  purpose_in_plot: ...

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

STAGE3_PROMPT = """Use only the provided text and the Stage-2 character list. Identify which existing characters fulfill the narrative roles hero, villain, and victim.

Rules:
- Pick at most one hero and one villain ("none" if no clear fit).
- Victim may include multiple characters separated by semicolons; use "none" if not applicable.
- Only use character names/labels supplied in Stage 2.
- Provide a ≤25-word evidence quote or brief justification for each assigned role (even if "none").

Output exactly:
Hero_character: <Stage-2 name or "none">
Hero_evidence: "<≤25-word quote or brief justification>"

Villain_character: <Stage-2 name or "none">
Villain_evidence: "<≤25-word quote or brief justification>"

Victim_characters: <semicolon-separated Stage-2 names or "none">
Victim_evidence: "<≤25-word quote or brief justification>"

Metadata (do not change):
Title: {title}
Year: {year}
Central_conflict_from_stage1: {central_conflict}

Characters_from_stage2 (do not alter names; do not invent new ones):
{char_list}

Provided text begins:
{body}
"""

STAGE4_PROMPT = """Use only the provided text. For each character, estimate where their moral reasoning lies on two numeric scales:
- Universalism (−1) ↔ Particularism (+1)
- Deontological (−1) ↔ Consequentialist (+1)

Instructions:
- Always return numeric scores within [−1, +1]. Negative leans to the left label, positive to the right label.
- Provide a confidence score between 0 and 1 for every numeric estimate.
- Notes should combine rationale and a ≤35-word quote/timecode supporting the score.
- Fill values for Protagonist and Antagonist even if evidence is weak (use best estimate with low confidence if needed).
- Provide a film-level score on the same universalism ↔ particularism axis.

Output exactly these keys:
Protagonist_UP_score: <float in [-1,1]>
Protagonist_UP_confidence: <float in [0,1]>
Protagonist_UP_notes: "<rationale + evidence (≤35 words)>"
Protagonist_DC_score: <float in [-1,1]>
Protagonist_DC_confidence: <float in [0,1]>
Protagonist_DC_notes: "<rationale + evidence (≤35 words)>"

Antagonist_UP_score: <float in [-1,1]>
Antagonist_UP_confidence: <float in [0,1]>
Antagonist_UP_notes: "<rationale + evidence>"
Antagonist_DC_score: <float in [-1,1]>
Antagonist_DC_confidence: <float in [0,1]>
Antagonist_DC_notes: "<rationale + evidence>"

Film_UP_score: <float in [-1,1]>
Film_UP_confidence: <float in [0,1]>
Film_UP_notes: "<rationale + evidence>"

Metadata:
Title: {title}
Year: {year}
Stage3_roles: {roles_summary}

Provided text begins:
{body}
"""

STAGE5_PROMPT = """Use only the provided text.

List up to two salient social groups treated as collective actors.

Output exactly these keys (omit Group_2_* if only one group; omit both if none and set flags to "none"):
Group_1_label: <short text or "none">
Group_1_type: <nation | local_community | family | profession | company | government_branch | movement | other | none>
Group_1_relation_to_protagonist: <in_group | out_group | unclear | none>
Group_1_portrayal: <positive | negative | mixed | neutral | none>
Group_1_is_threatened: <yes | no | unclear | none>
Group_1_evidence: "<≤25-word quote or "none">"

Group_2_label: <...>  # optional if a second group exists
Group_2_type: <...>
Group_2_relation_to_protagonist: <...>
Group_2_portrayal: <...>
Group_2_is_threatened: <...>
Group_2_evidence: "<...>"

parochialism_flag: <1 | 0 | none>
outgroup_blame_flag: <1 | 0 | none>

If no salient groups are identified, set Group_1_label to "none" and omit Group_2_* keys.

Metadata:
Title: {title}
Year: {year}

Provided text begins:
{body}
"""
