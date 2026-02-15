"""
Deterministic format parsers for corpus_prepare.

Each parser returns list[dict] with keys: title (str), content (str), metadata (dict, optional).
No LLM calls — pure file I/O and heuristics.
"""

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".jsonl", ".csv", ".pdf"}

# Ordered priority lists for auto-detecting fields
TEXT_FIELD_NAMES = [
    "content", "context", "text", "body", "message",
    "description", "tweet", "post", "abstract", "summary",
]
TITLE_FIELD_NAMES = [
    "title", "name", "subject", "headline", "author", "id",
]
ARRAY_WRAPPER_KEYS = [
    "results", "data", "items", "records", "documents", "entries", "rows",
]


def parse_file(filepath: Path) -> List[Dict[str, Any]]:
    """Dispatch to the correct parser based on file extension.

    Args:
        filepath: Path to the file to parse.

    Returns:
        List of dicts with 'title', 'content', and optionally 'metadata'.

    Raises:
        ValueError: If the file format is unsupported or content field can't be detected.
    """
    ext = filepath.suffix.lower()
    parsers = {
        ".txt": parse_text_file,
        ".md": parse_text_file,
        ".json": parse_json_file,
        ".jsonl": parse_jsonl_file,
        ".csv": parse_csv_file,
        ".pdf": parse_pdf_file,
    }
    parser = parsers.get(ext)
    if parser is None:
        raise ValueError(
            f"Unsupported file format '{ext}' for {filepath.name}. "
            f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )
    return parser(filepath)


def parse_text_file(filepath: Path) -> List[Dict[str, Any]]:
    """Parse a .txt or .md file as a single document."""
    content = filepath.read_text(encoding="utf-8")
    return [{"title": filepath.stem, "content": content}]


def parse_json_file(filepath: Path) -> List[Dict[str, Any]]:
    """Parse a .json file. Auto-unwraps arrays and detects text/title fields."""
    raw = json.loads(filepath.read_text(encoding="utf-8"))
    records = _unwrap_json(raw, filepath.name)

    if isinstance(records, dict):
        # Single object — treat as one document
        records = [records]

    if not isinstance(records, list):
        raise ValueError(
            f"Expected JSON array or object in {filepath.name}, got {type(records).__name__}"
        )

    if not records:
        logger.warning(f"Empty JSON array in {filepath.name}")
        return []

    text_field = _detect_field(records[0], TEXT_FIELD_NAMES)
    if text_field is None:
        available = sorted(records[0].keys())
        raise ValueError(
            f"Cannot detect text field in {filepath.name}. "
            f"Available keys: {available}. "
            f"Expected one of: {TEXT_FIELD_NAMES}"
        )
    logger.info(f"{filepath.name}: using '{text_field}' as text field")

    title_field = _detect_field(records[0], TITLE_FIELD_NAMES)
    if title_field:
        logger.info(f"{filepath.name}: using '{title_field}' as title field")

    return _records_to_entries(records, text_field, title_field, filepath.stem)


def parse_jsonl_file(filepath: Path) -> List[Dict[str, Any]]:
    """Parse a .jsonl file (one JSON object per line)."""
    records = []
    for i, line in enumerate(filepath.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON on line {i + 1} of {filepath.name}: {e}") from e

    if not records:
        logger.warning(f"Empty JSONL file: {filepath.name}")
        return []

    text_field = _detect_field(records[0], TEXT_FIELD_NAMES)
    if text_field is None:
        available = sorted(records[0].keys())
        raise ValueError(
            f"Cannot detect text field in {filepath.name}. "
            f"Available keys: {available}. "
            f"Expected one of: {TEXT_FIELD_NAMES}"
        )
    logger.info(f"{filepath.name}: using '{text_field}' as text field")

    title_field = _detect_field(records[0], TITLE_FIELD_NAMES)
    if title_field:
        logger.info(f"{filepath.name}: using '{title_field}' as title field")

    return _records_to_entries(records, text_field, title_field, filepath.stem)


def parse_csv_file(filepath: Path) -> List[Dict[str, Any]]:
    """Parse a .csv file using csv.DictReader. Auto-detects text/title columns."""
    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file {filepath.name} has no header row")

        # Detect fields from header
        first_row_keys = {k: k for k in reader.fieldnames}
        text_field = _detect_field(first_row_keys, TEXT_FIELD_NAMES)
        if text_field is None:
            raise ValueError(
                f"Cannot detect text column in {filepath.name}. "
                f"Available columns: {reader.fieldnames}. "
                f"Expected one of: {TEXT_FIELD_NAMES}"
            )
        logger.info(f"{filepath.name}: using '{text_field}' as text column")

        title_field = _detect_field(first_row_keys, TITLE_FIELD_NAMES)
        if title_field:
            logger.info(f"{filepath.name}: using '{title_field}' as title column")

        records = list(reader)

    return _records_to_entries(records, text_field, title_field, filepath.stem)


def parse_pdf_file(filepath: Path) -> List[Dict[str, Any]]:
    """Parse a .pdf file using pypdf. Concatenates all pages into one document."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise ImportError(
            "pypdf is required to parse PDF files. Install with: pip install pypdf"
        ) from e

    reader = PdfReader(str(filepath))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)

    if not pages:
        raise ValueError(f"No extractable text in PDF: {filepath.name}")

    content = "\n\n".join(pages)
    return [{"title": filepath.stem, "content": content}]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unwrap_json(raw: Any, filename: str) -> Any:
    """Unwrap a JSON object that wraps an array in a known key."""
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return raw

    # Check known wrapper keys
    for key in ARRAY_WRAPPER_KEYS:
        if key in raw and isinstance(raw[key], list):
            logger.info(f"{filename}: unwrapped array from key '{key}'")
            return raw[key]

    # Fallback: if exactly one key holds an array, use it
    array_keys = [k for k, v in raw.items() if isinstance(v, list)]
    if len(array_keys) == 1:
        key = array_keys[0]
        logger.info(f"{filename}: unwrapped array from single array key '{key}'")
        return raw[key]

    # No array found — treat the dict itself as a single record
    return raw


def _detect_field(record: dict, candidates: List[str]) -> str | None:
    """Return the first candidate key present in the record, or None."""
    # Case-insensitive matching
    lower_map = {k.lower(): k for k in record.keys()}
    for candidate in candidates:
        if candidate in lower_map:
            return lower_map[candidate]
    return None


def _records_to_entries(
    records: List[dict],
    text_field: str,
    title_field: str | None,
    fallback_title: str,
) -> List[Dict[str, Any]]:
    """Convert raw records to corpus entries with title, content, metadata."""
    entries = []
    for i, record in enumerate(records):
        content = record.get(text_field)
        if content is None or (isinstance(content, str) and not content.strip()):
            continue
        content = str(content)

        if title_field and record.get(title_field):
            title = str(record[title_field])
        else:
            title = f"{fallback_title}_{i}"

        entry: Dict[str, Any] = {"title": title, "content": content}

        # Preserve non-content, non-title fields as metadata
        skip_keys = {text_field}
        if title_field:
            skip_keys.add(title_field)
        metadata = {k: v for k, v in record.items() if k not in skip_keys}
        if metadata:
            entry["metadata"] = metadata

        entries.append(entry)

    return entries
