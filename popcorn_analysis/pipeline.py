"\"\"\"High-level orchestration for running the multi-stage analysis.\"\"\""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from . import aggregation, data, parsers, prompts
from .llm_client import LLMClient, cache_path, read_cache, write_cache
from .utils import ParseError, load_json, save_json

LOGGER = logging.getLogger(__name__)


STAGE_ORDER = ["stage1", "stage2", "stage3", "stage4", "stage5"]


@dataclass
class PipelineConfig:
    data_file: Path
    master_csv: Path
    aggregate_csv: Path
    output_dir: Path
    cache_dir: Optional[Path] = None
    stages: Sequence[str] = tuple(STAGE_ORDER)
    max_parse_attempts: int = 3
    resume: bool = True


class AnalysisPipeline:
    def __init__(self, llm_client: LLMClient, config: PipelineConfig):
        self.llm = llm_client
        self.config = config
        self.output_dir = config.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = config.cache_dir or (self.output_dir / "_raw_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.films = data.load_films_from_jsonl(config.data_file)
        # Load master rows (prefer aggregate if it exists).
        if config.aggregate_csv.exists():
            LOGGER.info("Loading existing aggregated CSV: %s", config.aggregate_csv)
            self.master_rows = data.load_master_csv(config.aggregate_csv)
        else:
            LOGGER.info("Loading base master CSV: %s", config.master_csv)
            self.master_rows = data.load_master_csv(config.master_csv)
        self.master_index = {row["movie_id"]: row for row in self.master_rows if row.get("movie_id")}

    def run(
        self,
        film_ids: Optional[Iterable[str]] = None,
        limit: Optional[int] = None,
    ) -> None:
        target_ids = set(film_ids) if film_ids else None
        processed = 0
        for film in self.films:
            if target_ids and film.movie_id not in target_ids:
                continue
            if limit is not None and processed >= limit:
                break
            LOGGER.info("Processing %s (%s)", film.title, film.movie_id)
            stage_results = self._run_film_stages(film)
            self._update_master_row(film, stage_results)
            processed += 1
        self._write_aggregate()

    # ------------------------------------------------------------------ #
    # Stage execution helpers
    # ------------------------------------------------------------------ #

    def _stage_path(self, stage: str, film_id: str) -> Path:
        return self.output_dir / stage / f"{film_id}.json"

    def _load_stage(self, stage: str, film_id: str) -> Optional[Dict]:
        path = self._stage_path(stage, film_id)
        if not path.exists():
            return None
        return load_json(path)

    def _save_stage(self, stage: str, film_id: str, payload: Dict) -> None:
        path = self._stage_path(stage, film_id)
        save_json(path, payload)

    def _run_film_stages(self, film: data.FilmRecord) -> Dict[str, Dict]:
        stage_data: Dict[str, Dict] = {}
        for stage in self.config.stages:
            path = self._stage_path(stage, film.movie_id)
            if path.exists() and self.config.resume:
                LOGGER.info("Stage %s already exists for %s; loading.", stage, film.movie_id)
                stage_data[stage] = load_json(path)
                continue
            LOGGER.info("Running stage %s for %s", stage, film.movie_id)
            stage_result = self._execute_stage(stage, film, stage_data)
            self._save_stage(stage, film.movie_id, stage_result)
            stage_data[stage] = stage_result
        return stage_data

    def _execute_stage(self, stage: str, film: data.FilmRecord, stage_data: Dict[str, Dict]) -> Dict:
        if stage not in STAGE_ORDER:
            raise ValueError(f"Unknown stage: {stage}")
        prompt_text = self._build_prompt(stage, film, stage_data)
        cache_file = cache_path(self.cache_dir, film.movie_id, stage, prompt_text, prompts.PROMPT_VERSION[stage])
        raw = read_cache(cache_file)
        attempts = 0
        while attempts < self.config.max_parse_attempts:
            attempts += 1
            if raw is None:
                raw = self.llm.generate(prompt_text)
                write_cache(cache_file, raw)
            try:
                parsed = self._parse_stage(stage, raw)
                return parsed
            except ParseError as exc:
                LOGGER.warning("Parse error on stage %s attempt %s for %s: %s", stage, attempts, film.movie_id, exc)
                if cache_file.exists():
                    error_path = cache_file.with_suffix(cache_file.suffix + ".error")
                    cache_file.replace(error_path)
                raw = None  # force re-generation
        raise RuntimeError(f"Failed to parse stage {stage} output for {film.movie_id} after {self.config.max_parse_attempts} attempts.")

    def _build_prompt(self, stage: str, film: data.FilmRecord, stage_data: Dict[str, Dict]) -> str:
        body = film.combined_text()
        year_text = film.year if film.year is not None else "not stated"
        title = film.title

        if stage == "stage1":
            return prompts.STAGE1_PROMPT.format(title=title, year=year_text, body=body)
        if stage == "stage2":
            prev = stage_data.get("stage1") or self._load_stage("stage1", film.movie_id)
            if not prev:
                raise RuntimeError("Stage 1 output required for Stage 2 prompt.")
            return prompts.STAGE2_PROMPT.format(
                title=title,
                year=year_text,
                central_conflict=prev["central_conflict_text"],
                body=body,
            )
        if stage == "stage3":
            s1 = stage_data.get("stage1") or self._load_stage("stage1", film.movie_id)
            s2 = stage_data.get("stage2") or self._load_stage("stage2", film.movie_id)
            if not s1 or not s2:
                raise RuntimeError("Stages 1 and 2 outputs required for Stage 3 prompt.")
            return prompts.STAGE3_PROMPT.format(
                title=title,
                year=year_text,
                central_conflict=s1["central_conflict_text"],
                char_list=s2["raw"],
                body=body,
            )
        if stage == "stage4":
            s3 = stage_data.get("stage3") or self._load_stage("stage3", film.movie_id)
            if not s3:
                raise RuntimeError("Stage 3 output required for Stage 4 prompt.")
            roles_summary = "\n".join(s3["raw"].splitlines()[:20])
            return prompts.STAGE4_PROMPT.format(
                title=title,
                year=year_text,
                roles_summary=roles_summary,
                body=body,
            )
        if stage == "stage5":
            return prompts.STAGE5_PROMPT.format(title=title, year=year_text, body=body)
        raise ValueError(f"Unsupported stage: {stage}")

    def _parse_stage(self, stage: str, raw: str) -> Dict:
        if stage == "stage1":
            return parsers.parse_stage1(raw)
        if stage == "stage2":
            return parsers.parse_stage2(raw)
        if stage == "stage3":
            return parsers.parse_stage3(raw)
        if stage == "stage4":
            return parsers.parse_stage4(raw)
        if stage == "stage5":
            return parsers.parse_stage5(raw)
        raise ValueError(f"Unsupported stage: {stage}")

    # ------------------------------------------------------------------ #
    # Aggregation helpers
    # ------------------------------------------------------------------ #

    def _update_master_row(self, film: data.FilmRecord, stage_results: Dict[str, Dict]) -> None:
        stages = {}
        for stage in STAGE_ORDER:
            payload = stage_results.get(stage) or self._load_stage(stage, film.movie_id)
            if payload:
                stages[stage] = payload
        flattened = aggregation.flatten_all(film, stages)
        row = self.master_index.get(film.movie_id)
        if row is None:
            row = {"movie_id": film.movie_id, "title": film.title, "year": str(film.year) if film.year else ""}
            self.master_rows.append(row)
            self.master_index[film.movie_id] = row
        row.update(flattened)
        # Preserve existing summary/subtitle file paths if present in film record
        if "summary_file" in row and not row["summary_file"]:
            row["summary_file"] = film.summary_file
        if "subtitle_file" in row and not row["subtitle_file"]:
            row["subtitle_file"] = film.subtitle_file
        if "tmdb_id" in row and not row["tmdb_id"]:
            pass  # already populated in master list

    def _write_aggregate(self) -> None:
        data.write_master_csv(self.config.aggregate_csv, self.master_rows)
        LOGGER.info("Wrote aggregated CSV to %s", self.config.aggregate_csv)

    # ------------------------------------------------------------------ #
    # Aggregate-only helper
    # ------------------------------------------------------------------ #

    def refresh_aggregate(self, film_ids: Optional[Iterable[str]] = None) -> None:
        """Rebuild the aggregated CSV using existing stage outputs without new LLM calls."""
        target_ids = set(film_ids) if film_ids else None
        for film in self.films:
            if target_ids and film.movie_id not in target_ids:
                continue
            stages: Dict[str, Dict] = {}
            for stage in STAGE_ORDER:
                payload = self._load_stage(stage, film.movie_id)
                if payload:
                    stages[stage] = payload
            if not stages:
                continue
            flattened = aggregation.flatten_all(film, stages)
            row = self.master_index.get(film.movie_id)
            if row is None:
                row = {"movie_id": film.movie_id, "title": film.title, "year": str(film.year) if film.year else ""}
                self.master_rows.append(row)
                self.master_index[film.movie_id] = row
            row.update(flattened)
        self._write_aggregate()
