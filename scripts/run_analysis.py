#!/usr/bin/env python3
"""Run multi-stage LLM analysis over prepared film data."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from popcorn_analysis.llm_client import LLMClient
from popcorn_analysis.pipeline import AnalysisPipeline, PipelineConfig, STAGE_ORDER


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run staged LLM analysis across films.")
    parser.add_argument(
        "--data-file",
        type=Path,
        default=Path.home() / "Desktop" / "processed_subs Kopie" / "prepared" / "paired_data.jsonl",
        help="JSONL file with film summary/subtitle data (default: prepared/paired_data.jsonl).",
    )
    parser.add_argument(
        "--master-csv",
        type=Path,
        default=Path.home() / "Desktop" / "processed_subs Kopie" / "prepared" / "master_list.csv",
        help="Path to the base master CSV produced during preprocessing.",
    )
    parser.add_argument(
        "--aggregate-csv",
        type=Path,
        default=Path.home() / "Desktop" / "processed_subs Kopie" / "prepared" / "master_list_with_analysis.csv",
        help="Destination CSV containing aggregated stage outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis_outputs"),
        help="Directory to store per-stage JSON outputs (default: ./analysis_outputs).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Optional directory for raw LLM response cache (defaults to <output-dir>/_raw_cache).",
    )
    parser.add_argument(
        "--stages",
        nargs="+",
        default=list(STAGE_ORDER),
        choices=STAGE_ORDER,
        help="List of stages to run (default: all stages).",
    )
    parser.add_argument(
        "--film-id",
        action="append",
        default=None,
        help="Specific movie_id to process (can be specified multiple times).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N matching films.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="OpenAI model name (default: gpt-4o-mini).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (default: 0.0).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Max API retry attempts (default: 5).",
    )
    parser.add_argument(
        "--max-parse-attempts",
        type=int,
        default=3,
        help="Max parse retries per stage before failing (default: 3).",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable resume mode (always re-run stages even if JSON exists).",
    )
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Skip LLM calls and rebuild the aggregated CSV from existing stage outputs.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (default: INFO).",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")

    class NullLLM:
        def generate(self, prompt: str) -> str:
            raise RuntimeError("LLM client not initialised; rerun without --aggregate-only.")

    if args.aggregate_only:
        llm_client = NullLLM()
    else:
        llm_client = LLMClient(
            model=args.model,
            temperature=args.temperature,
            max_retries=args.max_retries,
        )

    config = PipelineConfig(
        data_file=args.data_file,
        master_csv=args.master_csv,
        aggregate_csv=args.aggregate_csv,
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        stages=args.stages,
        max_parse_attempts=args.max_parse_attempts,
        resume=not args.no_resume,
    )

    pipeline = AnalysisPipeline(llm_client, config)

    if args.aggregate_only:
        pipeline.refresh_aggregate(film_ids=args.film_id)
        return 0

    pipeline.run(film_ids=args.film_id, limit=args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
