"\"\"\"Enumerations used across analysis stages.\"\"\""

TOPIC = {
    "relationships_family",
    "crime_justice",
    "war_security",
    "politics_governance",
    "finance_business",
    "science_technology",
    "disaster_crisis",
    "supernatural_fantasy",
    "society_culture",
    "other",
    "not_stated",
}

CONFLICT_TYPE = {
    "violent_confrontation",
    "pursuit_escape",
    "survival",
    "investigation_quest",
    "crime_heist_competition",
    "institutional_legal_political",
    "romantic_interpersonal",
    "deception_intrigue",
    "other",
    "not_stated",
}

HUMAN_TIER2 = {
    "government_official",
    "security_military_police",
    "corporate",
    "criminal",
    "terrorist",
    "scientist_engineer_expert",
    "journalist_media",
    "civilian_individual_or_community",
    "legal_judicial",
    "health_medical",
    "other_human",
}

INSTRUMENT_TIER2 = {
    "technology_system",
    "financial_system_or_instrument",
    "regulation_law_policy",
    "environment_natural_disaster",
    "disease_pathogen",
    "supernatural_magic",
    "other_instrument",
}

TIER1 = {"human", "instrument"}
STANCE = {"supports", "opposes", "mixed/neutral"}
MOTIVE = {"personal_gain", "ideological", "duty_service", "profit", "justice", "survival", "other", "not_stated"}
GENDER = {"male", "female", "other_undefined"}
RACE = {"caucasian", "person_of_color", "other_undefined"}
PURPOSE_IN_PLOT = {"threat", "constraint", "tool", "background", "not_stated"}

ROLES = {"hero", "villain", "victim", "ambiguous", "none"}

UP_LABEL = {"universalist", "particularist", "mixed/unclear", "none"}
DC_LABEL = {"deontological", "consequentialist", "mixed/unclear", "none"}

GROUP_TYPE = {"nation", "local_community", "family", "profession", "company", "government_branch", "movement", "other"}
RELATION_TO_PROTAGONIST = {"in_group", "out_group", "unclear"}
PORTRAYAL = {"positive", "negative", "mixed", "neutral"}
YES_NO_UNCLEAR = {"yes", "no", "unclear"}
FLAG_01_NONE = {"1", "0", "none"}
