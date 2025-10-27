from __future__ import annotations

import csv
import json
import re
import ssl
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


BRACKET_RE = re.compile(r"\[[^\]]*\]|\([^\)]*\)")
TIMESTAMP_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}$"
)
NON_WORD_RE = re.compile(r"[^a-z0-9]+")
WHITESPACE_RE = re.compile(r"\s+")

NOISE_TOKENS = {
    "1080p",
    "720p",
    "480p",
    "ac3",
    "aac",
    "amzn",
    "bd",
    "bdrip",
    "bluray",
    "brrip",
    "cam",
    "dd51",
    "divx",
    "dts",
    "dvdrip",
    "eng",
    "extended",
    "hdrip",
    "imax",
    "new",
    "proper",
    "remaster",
    "remastered",
    "remastered",
    "remux",
    "rip",
    "sparks",
    "playnow",
    "hdclub",
    "dvd5",
    "pal",
    "nbs",
    "unseen",
    "collector",
    "collectors",
    "edition",
    "esir",
    "ultimate",
    "anniversary",
    "subbed",
    "summary",
    "unrated",
    "v2",
    "webrip",
    "webdl",
    "x264",
    "xvid",
    "yify",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class DatasetConfig:
    base_dir: Path
    output_dir: Path
    min_score: float = 0.6
    sample: Optional[int] = None
    csv_path: Optional[Path] = None
    imdb_metadata: bool = False
    imdb_timeout: float = 10.0
    imdb_cache: Optional[Path] = None
    tmdb_metadata: bool = False
    tmdb_api_key: Optional[str] = None
    tmdb_bearer_token: Optional[str] = None
    tmdb_timeout: float = 10.0
    tmdb_cache: Optional[Path] = None


class TitleNormalizer:
    """Handle normalisation of file stems into comparison keys and display titles."""

    def normalise(self, stem: str) -> Tuple[str, str]:
        scrubbed = BRACKET_RE.sub(" ", stem)
        scrubbed = scrubbed.replace(".", " ").replace("_", " ").replace("-", " ")
        scrubbed = scrubbed.lower()
        scrubbed = re.sub(r"\b(19|20)\d{2}\b", " ", scrubbed)
        raw_tokens = scrubbed.split()
        tokens = [
            token
            for token in raw_tokens
            if token not in NOISE_TOKENS
            and not (any(ch.isdigit() for ch in token) and not token.isdigit())
        ]
        comparison = NON_WORD_RE.sub(" ", " ".join(tokens)).strip()
        comparison = WHITESPACE_RE.sub(" ", comparison)
        display_tokens = [token.capitalize() for token in tokens if token]
        display_title = " ".join(display_tokens) or stem
        return comparison, display_title


class SubtitleCleaner:
    """Strip styling, numbering, and timing cues from SRT files."""

    def clean(self, text: str) -> str:
        cleaned: List[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.isdigit():
                continue
            if TIMESTAMP_RE.match(line):
                continue
            if line.startswith("{\\") or line.startswith("{#"):
                continue
            if BRACKET_RE.fullmatch(line):
                continue
            line = BRACKET_RE.sub(" ", line)
            line = re.sub(r"<[^>]+>", " ", line)
            line = WHITESPACE_RE.sub(" ", line).strip()
            if line:
                cleaned.append(line)
        return "\n".join(cleaned)


class SummaryCleaner:
    """Normalise whitespace within summary files."""

    def clean(self, text: str) -> str:
        return WHITESPACE_RE.sub(" ", text).strip()


def detect_year(stem: str) -> Optional[int]:
    match = re.match(r"^(19|20)\d{2}", stem)
    if match:
        try:
            return int(match.group())
        except ValueError:
            return None
    return None


@dataclass
class MediaFile:
    path: Path
    normalized: str
    display_title: str
    year: Optional[int]

    def slug(self) -> str:
        pieces: List[str] = []
        if self.year:
            pieces.append(str(self.year))
        base = self.normalized or self.display_title.lower()
        slug = NON_WORD_RE.sub("-", base).strip("-")
        pieces.append(slug or self.path.stem.lower())
        return "-".join(filter(None, pieces))


class MediaLibrary:
    def __init__(self, base_dir: Path, normalizer: TitleNormalizer):
        self.base_dir = base_dir
        self.subtitle_dir = base_dir / "subtitles"
        self.summary_dir = base_dir / "summaries"
        self.normalizer = normalizer

    def _load(self, folder: Path, suffix: str) -> List[MediaFile]:
        files: List[MediaFile] = []
        for path in sorted(folder.rglob(f"*{suffix}")):
            if not path.is_file():
                continue
            stem = path.stem
            comparison, display = self.normalizer.normalise(stem)
            files.append(
                MediaFile(
                    path=path,
                    normalized=comparison,
                    display_title=display,
                    year=detect_year(stem),
                )
            )
        return files

    def load_subtitles(self) -> List[MediaFile]:
        if not self.subtitle_dir.is_dir():
            raise FileNotFoundError(f"Subtitle directory not found: {self.subtitle_dir}")
        return self._load(self.subtitle_dir, ".srt")

    def load_summaries(self) -> List[MediaFile]:
        if not self.summary_dir.is_dir():
            raise FileNotFoundError(f"Summary directory not found: {self.summary_dir}")
        return self._load(self.summary_dir, ".txt")


class MediaPairer:
    def __init__(self, min_score: float):
        self.min_score = min_score

    def pair(
        self, summaries: Sequence[MediaFile], subtitles: Sequence[MediaFile]
    ) -> Tuple[List[Tuple[MediaFile, MediaFile, float]], List[MediaFile], List[MediaFile]]:
        matches: List[Tuple[MediaFile, MediaFile, float]] = []
        unmatched_summaries: List[MediaFile] = []
        used_subtitles: set[Path] = set()

        for summary in summaries:
            summary_key = summary.normalized or summary.display_title.lower()
            best: Optional[Tuple[MediaFile, float]] = None
            for subtitle in subtitles:
                if subtitle.path in used_subtitles:
                    continue
                subtitle_key = subtitle.normalized or subtitle.display_title.lower()
                if not summary_key or not subtitle_key:
                    continue
                score = SequenceMatcher(None, summary_key, subtitle_key).ratio()
                if best is None or score > best[1]:
                    best = (subtitle, score)
            if best and best[1] >= self.min_score:
                matches.append((summary, best[0], best[1]))
                used_subtitles.add(best[0].path)
            else:
                unmatched_summaries.append(summary)

        unmatched_subtitles = [
            subtitle for subtitle in subtitles if subtitle.path not in used_subtitles
        ]
        return matches, unmatched_summaries, unmatched_subtitles


@dataclass
class DatasetRecord:
    movie_id: str
    title: str
    year: Optional[int]
    summary_file: str
    subtitle_file: str
    match_score: float
    summary_text: str
    subtitle_text: str
    imdb_id: Optional[str] = None
    release_date: Optional[str] = None
    tmdb_id: Optional[int] = None
    genres: List[str] = field(default_factory=list)

    def as_json(self) -> Dict[str, object]:
        return {
            "movie_id": self.movie_id,
            "title": self.title,
            "year": self.year,
            "summary_file": self.summary_file,
            "subtitle_file": self.subtitle_file,
            "match_score": self.match_score,
            "summary_text": self.summary_text,
            "subtitle_text": self.subtitle_text,
            "imdb_id": self.imdb_id,
            "release_date": self.release_date,
            "tmdb_id": self.tmdb_id,
            "genres": self.genres,
        }

    def as_csv_row(self) -> Dict[str, Optional[str]]:
        genre_string = ";".join(self.genres) if self.genres else ""
        return {
            "movie_id": self.movie_id,
            "title": self.title,
            "year": str(self.year) if self.year else "",
            "summary_file": self.summary_file,
            "subtitle_file": self.subtitle_file,
            "imdb_id": self.imdb_id or "",
            "release_date": self.release_date or "",
            "tmdb_id": str(self.tmdb_id) if self.tmdb_id is not None else "",
            "genres": genre_string,
        }


class DatasetWriter:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def ensure_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_jsonl(self, records: Iterable[DatasetRecord], path: Path) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record.as_json(), ensure_ascii=False) + "\n")

    def write_manifest(
        self,
        path: Path,
        config: DatasetConfig,
        summary_count: int,
        subtitle_count: int,
        paired: int,
        unmatched_summaries: int,
        unmatched_subtitles: int,
        imdb_populated: int,
        tmdb_populated: int,
    ) -> None:
        payload = {
            "base_dir": str(config.base_dir),
            "output_dir": str(self.output_dir),
            "min_score": config.min_score,
            "total_summaries": summary_count,
            "total_subtitles": subtitle_count,
            "paired": paired,
            "unmatched_summaries": unmatched_summaries,
            "unmatched_subtitles": unmatched_subtitles,
            "imdb_metadata": config.imdb_metadata,
            "with_imdb": imdb_populated,
            "tmdb_metadata": config.tmdb_metadata,
            "with_tmdb": tmdb_populated,
        }
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def write_unmatched(self, path: Path, items: Iterable[MediaFile], base_dir: Path) -> None:
        payload = [
            {
                "file": self._relativize(item.path, base_dir),
                "normalized": item.normalized,
                "display_title": item.display_title,
                "year": item.year,
            }
            for item in items
        ]
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def write_master_csv(self, path: Path, records: Iterable[DatasetRecord]) -> None:
        fieldnames = [
            "movie_id",
            "title",
            "year",
            "summary_file",
            "subtitle_file",
            "imdb_id",
            "release_date",
            "tmdb_id",
            "genres",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow(record.as_csv_row())

    @staticmethod
    def _relativize(path: Path, base_dir: Path) -> str:
        try:
            return str(path.relative_to(base_dir))
        except ValueError:
            return str(path)


@dataclass
class IMDbMetadata:
    imdb_id: str
    release_date: Optional[str] = None

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {"imdb_id": self.imdb_id, "release_date": self.release_date}


@dataclass
class IMDbCandidate:
    imdb_id: str
    title: str
    year: Optional[int]


class IMDbClient:
    """Fetch IMDb identifiers and release dates using IMDb suggestion endpoints."""

    suggestion_delay: float = 0.25

    def __init__(
        self,
        normalizer: Optional[TitleNormalizer] = None,
        timeout: float = 10.0,
        cache_path: Optional[Path] = None,
    ):
        self.normalizer = normalizer or TitleNormalizer()
        self.timeout = timeout
        self.cache_path = cache_path
        self._cache: Dict[str, Dict[str, Optional[str]]] = {}
        self._last_request: float = 0.0
        if self.cache_path and self.cache_path.exists():
            try:
                self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def lookup(self, title: str, year: Optional[int]) -> Optional[IMDbMetadata]:
        key = self._cache_key(title, year)
        if key in self._cache:
            cached = self._cache[key]
            imdb_id = cached.get("imdb_id")
            if imdb_id:
                return IMDbMetadata(imdb_id=imdb_id, release_date=cached.get("release_date"))

        candidates = self._search_candidates(title)
        if not candidates:
            return None

        best = self._select_candidate(title, year, candidates)
        if not best:
            return None

        release_date = self._fetch_release_date(best.imdb_id)
        metadata = IMDbMetadata(imdb_id=best.imdb_id, release_date=release_date)
        self._cache[key] = metadata.as_dict()
        return metadata

    def persist_cache(self) -> None:
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _cache_key(self, title: str, year: Optional[int]) -> str:
        normalized, _ = self.normalizer.normalise(title)
        return f"{normalized}|{year or ''}"

    def _search_candidates(self, title: str) -> List[IMDbCandidate]:
        slug = NON_WORD_RE.sub("_", title.lower()).strip("_")
        if not slug:
            return []
        first = slug[0]
        url = f"https://v2.sg.media-imdb.com/suggestion/{first}/{quote(slug)}.json"
        payload = self._request_json(url)
        if not payload:
            return []
        candidates: List[IMDbCandidate] = []
        for item in payload.get("d", []):
            imdb_id = item.get("id")
            if not imdb_id:
                continue
            candidates.append(
                IMDbCandidate(
                    imdb_id=imdb_id,
                    title=item.get("l", ""),
                    year=item.get("y"),
                )
            )
        return candidates

    def _select_candidate(
        self, title: str, year: Optional[int], candidates: Sequence[IMDbCandidate]
    ) -> Optional[IMDbCandidate]:
        target_norm, _ = self.normalizer.normalise(title)
        best: Optional[Tuple[IMDbCandidate, float]] = None
        for candidate in candidates:
            candidate_norm, _ = self.normalizer.normalise(candidate.title)
            score = SequenceMatcher(None, target_norm, candidate_norm).ratio()
            if year and candidate.year:
                if abs(candidate.year - year) <= 1:
                    score += 0.05
            if best is None or score > best[1]:
                best = (candidate, score)
        if best and best[1] >= 0.5:
            return best[0]
        return None

    def _fetch_release_date(self, imdb_id: str) -> Optional[str]:
        url = f"https://www.imdb.com/title/{imdb_id}/"
        html = self._request_text(url)
        if not html:
            return None
        match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if not match:
            return None
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            date = data.get("datePublished")
            if isinstance(date, str):
                return date
        return None

    def _request_json(self, url: str) -> Optional[Dict[str, object]]:
        text = self._request_text(url)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _request_text(self, url: str) -> Optional[str]:
        self._respect_rate_limit()
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="ignore")
        except (HTTPError, URLError, TimeoutError):
            return None

    def _respect_rate_limit(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self.suggestion_delay:
            time.sleep(self.suggestion_delay - elapsed)
        self._last_request = time.time()


@dataclass
class TMDBMetadata:
    tmdb_id: int
    imdb_id: Optional[str]
    release_date: Optional[str]
    genres: List[str]

    def as_dict(self) -> Dict[str, object]:
        return {
            "tmdb_id": self.tmdb_id,
            "imdb_id": self.imdb_id,
            "release_date": self.release_date,
            "genres": self.genres,
        }


@dataclass
class TMDBCandidate:
    tmdb_id: int
    title: str
    release_date: Optional[str]
    year: Optional[int]


class TMDBClient:
    """Fetch metadata from The Movie Database (TMDB) including IMDb ids and genres."""

    api_root = "https://api.themoviedb.org/3"

    def __init__(
        self,
        api_key: Optional[str] = None,
        bearer_token: Optional[str] = None,
        normalizer: Optional[TitleNormalizer] = None,
        timeout: float = 10.0,
        cache_path: Optional[Path] = None,
    ):
        if not api_key and not bearer_token:
            raise ValueError("TMDB API key or bearer token must be provided.")
        self.api_key = api_key
        self.bearer_token = bearer_token
        self.normalizer = normalizer or TitleNormalizer()
        self.timeout = timeout
        self.cache_path = cache_path
        self._cache: Dict[str, Dict[str, object]] = {}
        self._ssl_context = self._build_ssl_context()
        if self.cache_path and self.cache_path.exists():
            try:
                self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def lookup(self, title: str, year: Optional[int]) -> Optional[TMDBMetadata]:
        key = self._cache_key(title, year)
        if key in self._cache:
            cached = self._cache[key]
            tmdb_id = cached.get("tmdb_id")
            if tmdb_id:
                genres = cached.get("genres") or []
                if isinstance(genres, str):
                    genres = [g.strip() for g in genres.split(",") if g.strip()]
                return TMDBMetadata(
                    tmdb_id=int(tmdb_id),
                    imdb_id=cached.get("imdb_id"),
                    release_date=cached.get("release_date"),
                    genres=list(genres),
                )

        candidates: List[TMDBCandidate] = []
        for query in self._build_queries(title):
            candidates = self._search_candidates(query, year)
            if candidates:
                break
        if not candidates:
            return None

        best = self._select_candidate(title, year, candidates)
        if not best:
            return None

        details = self._fetch_details(best.tmdb_id)
        if not details:
            return None

        metadata = TMDBMetadata(
            tmdb_id=best.tmdb_id,
            imdb_id=details.get("imdb_id"),
            release_date=details.get("release_date"),
            genres=details.get("genres", []),
        )
        self._cache[key] = metadata.as_dict()
        return metadata

    def persist_cache(self) -> None:
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _cache_key(self, title: str, year: Optional[int]) -> str:
        normalized, _ = self.normalizer.normalise(title)
        return f"{normalized}|{year or ''}"

    def _search_candidates(self, query: str, year: Optional[int]) -> List[TMDBCandidate]:
        if not query:
            return []
        params = {"query": query, "include_adult": "false"}
        if year:
            params["year"] = year
        payload = self._request_json("/search/movie", params)
        if not payload:
            return []
        candidates: List[TMDBCandidate] = []
        for item in payload.get("results", []):
            tmdb_id = item.get("id")
            name = item.get("title") or item.get("original_title")
            release_date = item.get("release_date") or None
            if not tmdb_id or not name:
                continue
            release_year = None
            if release_date and len(release_date) >= 4:
                try:
                    release_year = int(release_date[:4])
                except ValueError:
                    release_year = None
            candidates.append(
                TMDBCandidate(
                    tmdb_id=int(tmdb_id),
                    title=name,
                    release_date=release_date,
                    year=release_year,
                )
            )
        return candidates

    def _select_candidate(
        self, title: str, year: Optional[int], candidates: Sequence[TMDBCandidate]
    ) -> Optional[TMDBCandidate]:
        target_norm, _ = self.normalizer.normalise(title)
        best: Optional[Tuple[TMDBCandidate, float]] = None
        for candidate in candidates:
            candidate_norm, _ = self.normalizer.normalise(candidate.title)
            score = SequenceMatcher(None, target_norm, candidate_norm).ratio()
            if year and candidate.year:
                if abs(candidate.year - year) <= 1:
                    score += 0.05
            if best is None or score > best[1]:
                best = (candidate, score)
        if best and best[1] >= 0.5:
            return best[0]
        return None

    def _fetch_details(self, tmdb_id: int) -> Optional[Dict[str, object]]:
        params = {"append_to_response": "external_ids"}
        payload = self._request_json(f"/movie/{tmdb_id}", params)
        if not payload:
            return None
        imdb_id = None
        external_ids = payload.get("external_ids")
        if isinstance(external_ids, dict):
            imdb_id = external_ids.get("imdb_id")
        release_date = payload.get("release_date") or None
        genres = []
        for item in payload.get("genres", []):
            name = item.get("name")
            if name:
                genres.append(str(name))
        return {
            "imdb_id": imdb_id,
            "release_date": release_date,
            "genres": genres,
        }

    def _build_queries(self, title: str, max_tokens: int = 6) -> List[str]:
        queries: List[str] = []
        normalized, _ = self.normalizer.normalise(title)
        tokens = normalized.split()
        tokens = [token for token in tokens if token]
        if tokens:
            max_len = min(len(tokens), max_tokens)
            for size in range(max_len, 1, -1):
                candidate = " ".join(tokens[:size])
                if candidate and candidate not in queries:
                    queries.append(candidate)
            joined = " ".join(tokens[:max_tokens])
            if joined and joined not in queries:
                queries.append(joined)
            if tokens[0] and tokens[0] not in queries:
                queries.append(tokens[0])
        if title and title not in queries:
            queries.append(title)
        return queries

    def _request_json(
        self, path: str, params: Optional[Dict[str, object]] = None
    ) -> Optional[Dict[str, object]]:
        url = f"{self.api_root}{path}"
        query_params = params.copy() if params else {}
        if self.api_key:
            query_params["api_key"] = self.api_key
        if query_params:
            clean_params = {
                key: value
                for key, value in query_params.items()
                if value not in (None, "")
            }
            url = f"{url}?{urlencode(clean_params)}"
        request = Request(url, headers=self._headers())
        try:
            with urlopen(request, timeout=self.timeout, context=self._ssl_context) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(charset, errors="ignore"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return None

    def _headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    @staticmethod
    def _build_ssl_context() -> ssl.SSLContext:
        context = ssl.create_default_context()
        cafile = Path("/etc/ssl/cert.pem")
        if cafile.exists():
            try:
                context.load_verify_locations(cafile=str(cafile))
            except ssl.SSLError:
                pass
        return context

class DatasetPipeline:
    def __init__(
        self,
        config: DatasetConfig,
        normalizer: Optional[TitleNormalizer] = None,
        subtitle_cleaner: Optional[SubtitleCleaner] = None,
        summary_cleaner: Optional[SummaryCleaner] = None,
    ):
        self.config = config
        self.normalizer = normalizer or TitleNormalizer()
        self.subtitle_cleaner = subtitle_cleaner or SubtitleCleaner()
        self.summary_cleaner = summary_cleaner or SummaryCleaner()
        self.library = MediaLibrary(config.base_dir, self.normalizer)
        self.pairer = MediaPairer(config.min_score)

    def run(self) -> Tuple[List[DatasetRecord], List[MediaFile], List[MediaFile]]:
        subtitles = self.library.load_subtitles()
        summaries = self.library.load_summaries()
        matches, unmatched_summaries, unmatched_subtitles = self.pairer.pair(
            summaries, subtitles
        )

        if self.config.sample is not None:
            matches = matches[: self.config.sample]

        records = self._build_records(matches)

        tmdb_client: Optional[TMDBClient] = None
        if self.config.tmdb_metadata:
            tmdb_client = TMDBClient(
                api_key=self.config.tmdb_api_key,
                bearer_token=self.config.tmdb_bearer_token,
                normalizer=self.normalizer,
                timeout=self.config.tmdb_timeout,
                cache_path=self.config.tmdb_cache,
            )
            for record in records:
                metadata = tmdb_client.lookup(record.title, record.year)
                if metadata:
                    record.tmdb_id = metadata.tmdb_id
                    if metadata.imdb_id and not record.imdb_id:
                        record.imdb_id = metadata.imdb_id
                    if metadata.release_date and not record.release_date:
                        record.release_date = metadata.release_date
                    if metadata.genres:
                        record.genres = metadata.genres
            tmdb_client.persist_cache()

        imdb_client: Optional[IMDbClient] = None
        if self.config.imdb_metadata:
            imdb_client = IMDbClient(
                normalizer=self.normalizer,
                timeout=self.config.imdb_timeout,
                cache_path=self.config.imdb_cache,
            )
            for record in records:
                if record.imdb_id and record.release_date:
                    continue
                metadata = imdb_client.lookup(record.title, record.year)
                if metadata:
                    record.imdb_id = metadata.imdb_id
                    record.release_date = metadata.release_date
            imdb_client.persist_cache()

        imdb_populated = sum(1 for record in records if record.imdb_id)
        tmdb_populated = sum(1 for record in records if record.tmdb_id is not None)

        writer = DatasetWriter(self.config.output_dir)
        writer.ensure_dir()

        paired_path = self.config.output_dir / "paired_data.jsonl"
        writer.write_jsonl(records, paired_path)
        writer.write_manifest(
            self.config.output_dir / "manifest.json",
            self.config,
            summary_count=len(summaries),
            subtitle_count=len(subtitles),
            paired=len(records),
            unmatched_summaries=len(unmatched_summaries),
            unmatched_subtitles=len(unmatched_subtitles),
            imdb_populated=imdb_populated,
            tmdb_populated=tmdb_populated,
        )
        writer.write_unmatched(
            self.config.output_dir / "unmatched_summaries.json",
            unmatched_summaries,
            self.config.base_dir,
        )
        writer.write_unmatched(
            self.config.output_dir / "unmatched_subtitles.json",
            unmatched_subtitles,
            self.config.base_dir,
        )

        csv_path = self.config.csv_path or (self.config.output_dir / "master_list.csv")
        writer.write_master_csv(csv_path, records)

        return records, unmatched_summaries, unmatched_subtitles

    def _build_records(
        self, matches: Sequence[Tuple[MediaFile, MediaFile, float]]
    ) -> List[DatasetRecord]:
        records: List[DatasetRecord] = []
        for summary, subtitle, score in matches:
            summary_text = self.summary_cleaner.clean(self._read_text(summary.path))
            subtitle_text = self.subtitle_cleaner.clean(self._read_text(subtitle.path))
            movie_id = summary.slug() or subtitle.slug()
            record = DatasetRecord(
                movie_id=movie_id,
                title=summary.display_title or subtitle.display_title,
                year=summary.year or subtitle.year,
                summary_file=self._relativize(summary.path),
                subtitle_file=self._relativize(subtitle.path),
                match_score=round(score, 3),
                summary_text=summary_text,
                subtitle_text=subtitle_text,
            )
            records.append(record)
        return records

    def _relativize(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.config.base_dir))
        except ValueError:
            return str(path)

    @staticmethod
    def _read_text(path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="ignore")
