"""JSONL streaming export writer.

Provides O(1) memory export by writing entities as they're fetched,
one JSON object per line.
"""

import json
import logging
from pathlib import Path
from typing import IO, Any

from strapi_kit.exceptions import ImportExportError
from strapi_kit.models.export_format import (
    ExportedEntity,
    ExportedMediaFile,
    ExportMetadata,
)

logger = logging.getLogger(__name__)


class JSONLExportWriter:
    """Streaming JSONL export writer.

    Writes entities one at a time to a JSONL file for memory-efficient
    export of large datasets.

    JSONL Format:
        Line 1: {"_type": "metadata", ...}
        Lines 2-N: {"_type": "entity", "content_type": "...", "data": {...}}
        Last line: {"_type": "media_manifest", "files": [...]}

    Example:
        >>> with JSONLExportWriter("export.jsonl") as writer:
        ...     writer.write_metadata(metadata)
        ...     for entity in entities:
        ...         writer.write_entity(entity)
        ...     writer.write_media_manifest(media_files)
    """

    def __init__(self, file_path: str | Path) -> None:
        """Initialize JSONL writer.

        Args:
            file_path: Path to output JSONL file
        """
        self.file_path = Path(file_path)
        self._file: IO[str] | None = None
        self._entity_count = 0
        self._content_type_counts: dict[str, int] = {}

    def __enter__(self) -> "JSONLExportWriter":
        """Open file for writing."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.file_path, "w", encoding="utf-8")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close file."""
        if self._file:
            self._file.close()
            self._file = None

    def write_metadata(self, metadata: ExportMetadata) -> None:
        """Write metadata as first line.

        Args:
            metadata: Export metadata
        """
        if not self._file:
            raise ImportExportError("Writer not opened - use context manager")

        record = {
            "_type": "metadata",
            **metadata.model_dump(mode="json"),
        }
        self._write_line(record)
        logger.debug("Wrote metadata to JSONL")

    def write_entity(self, entity: ExportedEntity) -> None:
        """Write a single entity.

        Args:
            entity: Entity to write
        """
        if not self._file:
            raise ImportExportError("Writer not opened - use context manager")

        record = {
            "_type": "entity",
            **entity.model_dump(mode="json"),
        }
        self._write_line(record)

        self._entity_count += 1
        ct = entity.content_type
        self._content_type_counts[ct] = self._content_type_counts.get(ct, 0) + 1

    def write_media_manifest(self, media_files: list[ExportedMediaFile]) -> None:
        """Write media manifest as final line.

        Args:
            media_files: List of media file references
        """
        if not self._file:
            raise ImportExportError("Writer not opened - use context manager")

        record = {
            "_type": "media_manifest",
            "files": [m.model_dump(mode="json") for m in media_files],
        }
        self._write_line(record)
        logger.debug(f"Wrote media manifest with {len(media_files)} files")

    def _write_line(self, record: dict[str, Any]) -> None:
        """Write a single JSON line.

        Args:
            record: Dictionary to serialize as JSON line
        """
        if self._file is None:
            raise ImportExportError("Writer not opened - use context manager")
        line = json.dumps(record, ensure_ascii=False, default=str)
        self._file.write(line + "\n")

    @property
    def entity_count(self) -> int:
        """Get total entities written."""
        return self._entity_count

    @property
    def content_type_counts(self) -> dict[str, int]:
        """Get entity counts per content type."""
        return self._content_type_counts.copy()
