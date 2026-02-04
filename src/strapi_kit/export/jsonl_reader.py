"""JSONL streaming import reader.

Provides O(1) memory import by reading entities one at a time.
"""

import json
import logging
from collections.abc import Generator
from pathlib import Path
from typing import IO, Any

from strapi_kit.exceptions import FormatError, ImportExportError
from strapi_kit.models.export_format import (
    ExportedEntity,
    ExportedMediaFile,
    ExportMetadata,
)

logger = logging.getLogger(__name__)


class JSONLImportReader:
    """Streaming JSONL import reader.

    Reads entities one at a time from a JSONL file for memory-efficient
    import of large datasets.

    Example:
        >>> with JSONLImportReader("export.jsonl") as reader:
        ...     metadata = reader.read_metadata()
        ...     for entity in reader.iter_entities():
        ...         process_entity(entity)
        ...     media_manifest = reader.read_media_manifest()
    """

    def __init__(self, file_path: str | Path) -> None:
        """Initialize JSONL reader.

        Args:
            file_path: Path to input JSONL file

        Raises:
            FormatError: If file doesn't exist
        """
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FormatError(f"JSONL file not found: {file_path}")

        self._file: IO[str] | None = None
        self._metadata: ExportMetadata | None = None
        self._media_manifest: list[ExportedMediaFile] | None = None
        self._current_line = 0

    def __enter__(self) -> "JSONLImportReader":
        """Open file for reading."""
        self._file = open(self.file_path, encoding="utf-8")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close file."""
        if self._file:
            self._file.close()
            self._file = None

    def read_metadata(self) -> ExportMetadata:
        """Read metadata from first line.

        Returns:
            Export metadata

        Raises:
            FormatError: If first line is not metadata
        """
        if not self._file:
            raise ImportExportError("Reader not opened - use context manager")

        if self._metadata is not None:
            return self._metadata

        line = self._file.readline()
        self._current_line = 1

        if not line:
            raise FormatError("Empty JSONL file")

        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            raise FormatError(f"Invalid JSON on line 1: {e}") from e

        if not isinstance(record, dict):
            raise FormatError(f"Expected JSON object on line 1, got: {type(record).__name__}")

        if record.get("_type") != "metadata":
            raise FormatError(f"Expected metadata on line 1, got: {record.get('_type')}")

        # Remove _type field before parsing
        record.pop("_type", None)
        self._metadata = ExportMetadata(**record)
        return self._metadata

    def iter_entities(self) -> Generator[ExportedEntity, None, None]:
        """Iterate over entities in the file.

        Yields entities one at a time for memory-efficient processing.

        Yields:
            ExportedEntity objects

        Raises:
            FormatError: If entity parsing fails
        """
        if not self._file:
            raise ImportExportError("Reader not opened - use context manager")

        # Ensure metadata is read first
        if self._metadata is None:
            self.read_metadata()

        for line in self._file:
            self._current_line += 1
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                raise FormatError(f"Invalid JSON on line {self._current_line}: {e}") from e

            if not isinstance(record, dict):
                raise FormatError(
                    f"Expected JSON object on line {self._current_line}, "
                    f"got: {type(record).__name__}"
                )

            record_type = record.get("_type")

            if record_type == "entity":
                record.pop("_type", None)
                yield ExportedEntity(**record)

            elif record_type == "media_manifest":
                # Parse and cache media manifest
                files_data = record.get("files", [])
                self._media_manifest = [ExportedMediaFile(**f) for f in files_data]
                # Don't yield - this is handled separately
                break

            elif record_type == "metadata":
                # Skip duplicate metadata
                continue

            else:
                logger.warning(f"Unknown record type on line {self._current_line}: {record_type}")

    def read_media_manifest(self) -> list[ExportedMediaFile]:
        """Read media manifest from file.

        Must be called after iter_entities() has completed, or will consume
        remaining entities to find the manifest.

        Returns:
            List of media file references, or empty list if no manifest found
        """
        if self._media_manifest is not None:
            return self._media_manifest

        # If we haven't read through entities yet, do so now
        if not self._file:
            raise ImportExportError("Reader not opened - use context manager")

        # Consume remaining lines to find media manifest
        for _ in self.iter_entities():
            pass  # Discard entities, we just want the manifest

        if self._media_manifest is None:
            # No media manifest found - return empty list
            return []

        return self._media_manifest

    def get_entity_count(self) -> int:
        """Count total entities without loading them all.

        Note: This reads through the entire file.

        Returns:
            Total entity count
        """
        count = 0
        # Create a new file handle to not disturb current position
        with open(self.file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("_type") == "entity":
                        count += 1
                except json.JSONDecodeError:
                    continue
        return count
