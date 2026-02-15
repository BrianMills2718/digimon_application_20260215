"""
Agent tool functions for corpus manipulation and management.
Each function takes its Pydantic input model and processes the corpus accordingly.
"""
import json
from pathlib import Path
from typing import Any

from Core.AgentSchema.corpus_tool_contracts import PrepareCorpusInputs, PrepareCorpusOutputs
from Core.AgentTools.corpus_format_parsers import SUPPORTED_EXTENSIONS, parse_file
from Core.Common.Logger import logger


async def prepare_corpus_from_directory(
    tool_input: PrepareCorpusInputs,
    main_config=None
) -> PrepareCorpusOutputs:
    """
    Process a directory of documents into a Corpus.json file in JSON Lines format.

    Supports: .txt, .md, .json, .jsonl, .csv, .pdf
    For structured formats (JSON, CSV), auto-detects content and title fields.

    Each document in the corpus will have:
    - 'title' (derived from filename or detected field)
    - 'content' (text content)
    - 'doc_id' (sequential identifier)
    - 'metadata' (optional, extra fields from structured formats)

    Args:
        tool_input: PrepareCorpusInputs with input_directory_path, output_directory_path,
                   and optionally target_corpus_name

    Returns:
        PrepareCorpusOutputs with processing results and corpus file path
    """
    try:
        input_dir = Path(tool_input.input_directory_path)
        output_dir = Path(tool_input.output_directory_path)

        # If input_dir is not absolute and doesn't exist, try common data directories
        if not input_dir.is_absolute() and not input_dir.exists():
            data_path = Path("Data") / input_dir
            if data_path.exists():
                input_dir = data_path
                logger.info(f"Resolved input directory to: {input_dir}")
            elif input_dir.exists():
                input_dir = input_dir.absolute()
            else:
                logger.warning(f"Could not find input directory: {tool_input.input_directory_path}")

        # Handle optional corpus name
        corpus_name = tool_input.target_corpus_name
        if not corpus_name:
            corpus_name = output_dir.name
            logger.info(f"No target_corpus_name provided, using derived name: {corpus_name}")

        # Validate input directory
        if not input_dir.is_dir():
            error_msg = f"Input directory '{input_dir}' not found or is not a directory."
            logger.error(error_msg)
            return PrepareCorpusOutputs(
                status="failure",
                message=error_msg,
                document_count=0
            )

        # Create output directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file_path = output_dir / "Corpus.json"

        # Collect all supported files (skip existing Corpus.json output files)
        all_files = []
        for ext in sorted(SUPPORTED_EXTENSIONS):
            for f in sorted(input_dir.glob(f"*{ext}")):
                if f.name == "Corpus.json":
                    continue
                all_files.append(f)

        ext_list = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        if not all_files:
            warning_msg = (
                f"No supported files found in {input_dir}. "
                f"Supported formats: {ext_list}"
            )
            logger.warning(warning_msg)
            return PrepareCorpusOutputs(
                status="failure",
                message=warning_msg,
                document_count=0,
                corpus_json_path=None
            )

        logger.info(
            f"Found {len(all_files)} file(s) in {input_dir} for corpus '{corpus_name}'"
        )

        corpus_data: list[dict[str, Any]] = []
        doc_id_counter = 0

        for filepath in all_files:
            try:
                entries = parse_file(filepath)
                for entry in entries:
                    corpus_entry: dict[str, Any] = {
                        "title": entry["title"],
                        "content": entry["content"],
                        "doc_id": doc_id_counter,
                    }
                    if "metadata" in entry:
                        corpus_entry["metadata"] = entry["metadata"]
                    corpus_data.append(corpus_entry)
                    doc_id_counter += 1
                logger.info(
                    f"Processed: {filepath.name} ({len(entries)} doc(s), "
                    f"doc_ids {doc_id_counter - len(entries)}-{doc_id_counter - 1})"
                )
            except Exception as e:
                logger.error(f"Error processing file {filepath.name}: {e}")

        if not corpus_data:
            warning_msg = (
                f"Failed to process any files in {input_dir}. "
                f"Supported formats: {ext_list}"
            )
            logger.warning(warning_msg)
            return PrepareCorpusOutputs(
                status="failure",
                message=warning_msg,
                document_count=0,
                corpus_json_path=None
            )

        # Write to Corpus.json in JSON Lines format
        try:
            with open(output_file_path, 'w', encoding='utf-8') as outfile:
                for entry in corpus_data:
                    json.dump(entry, outfile)
                    outfile.write('\n')

            success_msg = (
                f"Successfully created Corpus.json with {len(corpus_data)} documents "
                f"for corpus '{corpus_name}'"
            )
            logger.info(f"{success_msg} at: {output_file_path}")

            return PrepareCorpusOutputs(
                corpus_json_path=str(output_file_path),
                document_count=len(corpus_data),
                status="success",
                message=success_msg
            )
        except Exception as e:
            error_msg = f"Error writing Corpus.json: {e}"
            logger.error(error_msg)
            return PrepareCorpusOutputs(
                status="failure",
                message=error_msg,
                document_count=0,
                corpus_json_path=None
            )

    except Exception as e:
        error_msg = f"Unexpected error in prepare_corpus_from_directory: {e}"
        logger.exception(error_msg)
        return PrepareCorpusOutputs(
            status="failure",
            message=error_msg,
            document_count=0,
            corpus_json_path=None
        )
