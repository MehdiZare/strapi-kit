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

    def rewrite_metadata(self, metadata: ExportMetadata) -> None:
        """Replace the first JSONL line with updated metadata.

        Used after streaming so ``total_entities`` / ``total_media`` match
        what was written. Copies remaining lines through a sibling temp
        file (O(1) memory) and keeps metadata on line 1.

        This is a terminal operation: the file handle is closed and not
        reopened. Later ``write_entity`` / ``write_media_manifest`` calls
        raise ``ImportExportError``.

        Args:
            metadata: Export metadata with final totals

        Raises:
            ImportExportError: If the writer is closed, the file is empty,
                the first line is not JSON, or the first line is not
                metadata
        """
        if not self._file:
            raise ImportExportError("Writer not opened - use context manager")

        self._file.flush()
        self._file.close()
        self._file = None

        tmp_path = self.file_path.with_name(self.file_path.name + ".tmp")
        try:
            with (
                open(self.file_path, encoding="utf-8") as src,
                open(tmp_path, "w", encoding="utf-8") as dst,
            ):
                first = src.readline()
                if not first.strip():
                    raise ImportExportError("Cannot rewrite metadata of empty JSONL file")
                try:
                    existing = json.loads(first)
                except json.JSONDecodeError as e:
                    raise ImportExportError(
                        "Cannot rewrite metadata: first line is not JSON"
                    ) from e
                if not isinstance(existing, dict) or existing.get("_type") != "metadata":
                    raise ImportExportError("Cannot rewrite metadata: first line is not metadata")
                record = {
                    "_type": "metadata",
                    **metadata.model_dump(mode="json"),
                }
                dst.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                for line in src:
                    dst.write(line)
            tmp_path.replace(self.file_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        logger.debug(
            "Rewrote JSONL metadata totals entities=%s media=%s",
            metadata.total_entities,
            metadata.total_media,
        )

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
