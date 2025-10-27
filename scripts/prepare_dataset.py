#!/usr/bin/env python3
"""Command-line interface for preparing subtitle/summary datasets."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from popcorn_prep import DatasetConfig, DatasetPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean subtitles, pair with plot summaries, and export structured data."
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.home() / "Desktop" / "processed_subs Kopie",
        help="Root directory containing 'subtitles' and 'summaries'.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Destination directory for generated artifacts (default: <base>/prepared).",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.6,
        help="Minimum fuzzy-match score (0-1) to accept a subtitle/summary pair.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Limit processing to the top-N matches for experimentation.",
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=None,
        help="Optional explicit path for the master CSV list.",
    )
    parser.add_argument(
        "--imdb-metadata",
        action="store_true",
        help="Fetch IMDb identifiers and release dates for each paired title.",
    )
    parser.add_argument(
        "--imdb-cache",
        type=Path,
        default=None,
        help="Path to persist IMDb metadata cache (defaults to <output>/imdb_cache.json).",
    )
    parser.add_argument(
        "--imdb-timeout",
        type=float,
        default=10.0,
        help="Timeout in seconds for IMDb HTTP requests.",
    )
    parser.add_argument(
        "--tmdb-metadata",
        action="store_true",
        help="Fetch metadata from TMDB (IMDb id, release date, genres).",
    )
    parser.add_argument(
        "--tmdb-api-key",
        type=str,
        default=None,
        help="TMDB v3 API key (falls back to TMDB_API_KEY env var).",
    )
    parser.add_argument(
        "--tmdb-bearer-token",
        type=str,
        default=None,
        help="TMDB v4 read access token (falls back to TMDB_BEARER_TOKEN env var).",
    )
    parser.add_argument(
        "--tmdb-cache",
        type=Path,
        default=None,
        help="Path to persist TMDB metadata cache (defaults to <output>/tmdb_cache.json).",
    )
    parser.add_argument(
        "--tmdb-timeout",
        type=float,
        default=10.0,
        help="Timeout in seconds for TMDB HTTP requests.",
    )
    return parser.parse_args()


def resolve_path(candidate: Optional[Path]) -> Optional[Path]:
    if candidate is None:
        return None
    return candidate.expanduser().resolve()


def main() -> None:
    args = parse_args()

    base_dir = resolve_path(args.base_dir) or Path.cwd()
    output_dir = resolve_path(args.output_dir) if args.output_dir else (base_dir / "prepared")
    csv_path = resolve_path(args.csv_path)

    imdb_cache = resolve_path(args.imdb_cache)
    if args.imdb_metadata and imdb_cache is None:
        imdb_cache = output_dir / "imdb_cache.json"

    tmdb_cache = resolve_path(args.tmdb_cache)
    if args.tmdb_metadata and tmdb_cache is None:
        tmdb_cache = output_dir / "tmdb_cache.json"

    tmdb_api_key = args.tmdb_api_key or os.getenv("TMDB_API_KEY")
    tmdb_bearer = args.tmdb_bearer_token or os.getenv("TMDB_BEARER_TOKEN")
    if args.tmdb_metadata and not (tmdb_api_key or tmdb_bearer):
        raise SystemExit(
            "TMDB metadata requested but no credentials provided. "
            "Pass --tmdb-api-key/--tmdb-bearer-token or set TMDB_API_KEY/TMDB_BEARER_TOKEN."
        )

    config = DatasetConfig(
        base_dir=base_dir,
        output_dir=output_dir,
        min_score=args.min_score,
        sample=args.sample,
        csv_path=csv_path,
        imdb_metadata=args.imdb_metadata,
        imdb_timeout=args.imdb_timeout,
        imdb_cache=imdb_cache,
        tmdb_metadata=args.tmdb_metadata,
        tmdb_api_key=tmdb_api_key,
        tmdb_bearer_token=tmdb_bearer,
        tmdb_timeout=args.tmdb_timeout,
        tmdb_cache=tmdb_cache,
    )

    pipeline = DatasetPipeline(config)
    records, unmatched_summaries, unmatched_subtitles = pipeline.run()

    paired_count = len(records)
    imdb_count = sum(1 for record in records if record.imdb_id)
    tmdb_count = sum(1 for record in records if record.tmdb_id is not None)

    print(f"Paired titles: {paired_count}")
    print(f"IMDb metadata filled: {imdb_count}")
    print(f"TMDB metadata filled: {tmdb_count}")
    print(f"Unmatched summaries: {len(unmatched_summaries)}")
    print(f"Unmatched subtitles: {len(unmatched_subtitles)}")


if __name__ == "__main__":
    main()
