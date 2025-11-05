# Popcorn Narratives Analysis Pipeline

This repository prepares movie subtitles/plot summaries and runs a multi–stage LLM analysis over them.  
The workflow has two major parts:

1. **Data preparation** – cleaning SRT files, pairing them with summaries, and generating a master CSV.
2. **Analysis** – running staged prompts that extract story structure, characters, moral framing, and social dynamics.

The instructions below assume you are working from the root of this repo inside the `popcorn-narratives` virtual environment.

---

## 1. Environment Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # if you have one; otherwise install packages manually
```

Set your OpenAI API key once per session (or add it to `.venv/bin/activate`):

```bash
export OPENAI_API_KEY="sk-..."
```

All commands below assume the key is exported before running.

---

## 2. Data Preparation

The prep script expects the raw assets in `~/Desktop/processed_subs Kopie/` (as supplied in this project) with the structure:

```
processed_subs Kopie/
├── subtitles/    # .srt files
├── summaries/    # .txt plot summaries
└── (other folders ignored)
```

Run the preprocessing script to clean the data, pair subtitles with summaries, and populate metadata:

```bash
source .venv/bin/activate
python scripts/prepare_dataset.py
```

Key outputs (created under `processed_subs Kopie/prepared/`):

- `paired_data.jsonl` – cleaned text for each film (summary + subtitles).
- `master_list.csv` – base metadata (title, year, file paths, TMDB/IMDb data).
- `manifest.json` – run statistics (counts, pairing thresholds).
- `unmatched_*.json` – any subtitles/summaries that did not auto–pair.

Options:

- `--sample N` – run on only the first N matches.
- `--tmdb-metadata` – fetch IMDb id, release date, genres from TMDB (needs `TMDB_API_KEY` or `TMDB_BEARER_TOKEN` exported).
- `--imdb-metadata` – optional IMDb lookup (disabled by default).

---

## 3. Analysis Pipeline

### Overview

The analysis uses staged prompts to extract increasingly detailed information. The stages run sequentially per film and cache raw model responses in `analysis_outputs/` (or any directory you choose). The default stages:

 **Stage 1** – setting + central conflict + topic tags.
 **Stage 2** – protagonist/antagonist plus up to three additional characters with attributes (tier, stance, evidence, demographic fields).
 **Stage 3** – assigns existing characters to the roles hero, villain, victim (victim list may include multiple names).
 **Stage 4** – numeric moral framing (universalism ↔ particularism, deontological ↔ consequentialist) for protagonist, antagonist, and the film overall, along with confidence and supporting notes.
 **Stage 5** – identifies up to two social groups, their relation to the protagonist, portrayal, threat status, and flags for parochialism/out-group blame.

### Running the pipeline

```bash
source .venv/bin/activate
python scripts/run_analysis.py \
  --output-dir analysis_outputs_v2 \
  --aggregate-csv "/Users/<you>/Desktop/processed_subs Kopie/prepared/master_list_with_analysis_v2.csv" \
  --stages stage1 stage2 stage3 stage4 stage5 \
  --no-resume
```

Important flags:

- `--output-dir` – where parsed stage JSON and raw caches are stored. Use a new directory when schema changes (`analysis_outputs_v2`).
- `--aggregate-csv` – enriched master list created/updated after the run.
- `--stages` – subset of stages to run (default: all).
- `--film-id` – restrict processing to specific movie IDs.
- `--no-resume` – force regeneration even if stage JSON already exists.
- `--max-parse-attempts` – retries per stage before failing (default 3).

The CLI writes a snapshot at the end; to rebuild the aggregate CSV without calling the API, run:

```bash
python scripts/run_analysis.py --aggregate-only \
  --output-dir analysis_outputs_v2 \
  --aggregate-csv "/Users/<you>/Desktop/processed_subs Kopie/prepared/master_list_with_analysis_v2.csv"
```

### Outputs

```
analysis_outputs_v2/
├── stage1/film_id.json     # parsed outputs per stage
├── stage2/...
├── _raw_cache/
│   ├── stage1/film_id.raw.<hash>.txt
│   └── stage4/...          # raw LLM responses (for debugging)
└── ...
```

The aggregate CSV merges base metadata plus all stage fields:

- Stage 1 columns: `stage1_setting`, `stage1_central_conflict`, `stage1_topic`, etc.
- Stage 2 columns: `stage2_protagonist_name`, `stage2_antagonist_stance`, etc.
- Stage 3 columns: `stage3_hero_character`, `stage3_villain_evidence`, `stage3_victim_characters`, etc.
- Stage 4 columns: `stage4_protagonist_up_score`, `stage4_protagonist_dc_confidence`, `stage4_film_up_notes`, etc. (scores in [-1, 1], confidence in [0, 1]).
- Stage 5 columns: `stage5_group1_label`, `stage5_group2_portrayal`, `stage5_parochialism_flag`, etc.

---

## 4. Code Layout

```
popcorn_prep/
  core.py           # data-cleaning library (pairing, TMDB metadata, CSV writing)
  __init__.py

popcorn_analysis/
  pipeline.py       # orchestrates stage runs, caching, aggregation
  prompts.py        # prompt text & schema versions for each stage
  parsers.py        # strict parsers/validators for LLM outputs (JSON or key/value)
  llm_client.py     # OpenAI chat wrapper with retry & caching helpers
  aggregation.py    # flattens stage results into CSV columns
  data.py           # load/write helpers for JSONL, CSVs
  enums.py          # allowed categorical values
  utils.py          # JSON helpers & parsing errors

scripts/
  prepare_dataset.py  # CLI for preprocessing subtitles/summaries
  run_analysis.py     # CLI for staged analysis & aggregation
```

When the parser encounters malformed model output, the raw response is saved with `.error` extension inside `_raw_cache`, making it easier to inspect and debug.

---

## 5. Common Tasks

### Re-run a specific film from a given stage

```bash
python scripts/run_analysis.py \
  --output-dir analysis_outputs_v2 \
  --aggregate-csv "/Users/<you>/Desktop/processed_subs Kopie/prepared/master_list_with_analysis_v2.csv" \
  --stages stage3 stage4 stage5 \
  --film-id 1977-close-encounters-of-the-third-kind \
  --no-resume
```

### Refresh the aggregate CSV after manually inspecting stage outputs

```bash
python scripts/run_analysis.py --aggregate-only \
  --output-dir analysis_outputs_v2 \
  --aggregate-csv "/Users/<you>/Desktop/processed_subs Kopie/prepared/master_list_with_analysis_v2.csv"
```

### Use a different dataset location

The CLIs accept `--base-dir`, `--data-file`, `--output-dir`, and `--aggregate-csv` to point to alternative directories. See `python scripts/prepare_dataset.py --help` and `python scripts/run_analysis.py --help` for the full argument list.

---

## 6. Stage Reference Summary

| Stage | Purpose | Key Fields in CSV |
|-------|---------|-------------------|
| **Stage 1** | Setting, central conflict, topic/theme tags | `stage1_setting`, `stage1_topic`, `stage1_conflict_type`, `stage1_evidence` |
| **Stage 2** | Protagonist, antagonist, up to 3 additional characters with categories/demographics/evidence | `stage2_protagonist_tier2`, `stage2_antagonist_stance`, `stage2_additional_1_evidence`, ... |
| **Stage 3** | Assign Stage-2 characters to hero, villain, victim roles | `stage3_hero_character`, `stage3_victim_characters`, evidences |
| **Stage 4** | Numeric moral framing (UP/DC) with confidence & notes | `stage4_protagonist_up_score`, `stage4_antagonist_dc_confidence`, `stage4_film_up_notes` |
| **Stage 5** | Social group portrayal and parochialism flags | `stage5_group1_label`, `stage5_group1_portrayal`, `stage5_parochialism_flag`, etc. |

All evidence/notes fields are trimmed to ≤35 words to maintain consistency.

---

## 7. Troubleshooting

- **Parse errors** – the pipeline retries up to `--max-parse-attempts`; check `_raw_cache/stage*/<film>.txt.error` if it keeps failing. Fix the prompt/normalization and rerun with `--no-resume`.
- **TLS/SSL errors** – usually transient network issues. Re-run the command or switch networks/VPN.
- **CSV not updating** – the run crashes before `_write_aggregate` executes. Use the `--aggregate-only` command to refresh using existing stage JSON.

Feel free to extend prompts, parsers, or add new stages. Always bump the prompt/schema version in `prompts.py` whenever output shape changes.
