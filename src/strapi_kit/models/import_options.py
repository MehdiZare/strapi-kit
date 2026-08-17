"""Models for import configuration and options.

Defines how imported data should be processed and validated.
"""

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, Field


class ConflictResolution(StrEnum):
    """Strategy for handling conflicts during import.

    Conflicts are per ``(documentId, locale)``. A missing locale of an
    existing document is not a conflict.

    Attributes:
        SKIP: Skip locales that already exist; write missing locales
        UPDATE: Overwrite existing locales; write missing locales
        FAIL: Write missing locales (and later rows); do not overwrite
            existing locale fields or their outbound relations; then raise
            after the entity/relation/publish pass
    """

    SKIP = "skip"
    UPDATE = "update"
    FAIL = "fail"


class ImportOptions(BaseModel):
    """Configuration for import operations.

    Attributes:
        dry_run: Validate without actually importing
        conflict_resolution: How to handle existing entities
        import_media: Whether to import media files
        overwrite_media: Overwrite existing media files
        content_types: Specific content types to import (None = all)
        skip_relations: Skip importing relations (for initial pass)
        validate_relations: Validate relation targets exist
        batch_size: Batch size for bulk operations
        progress_callback: Optional progress callback(current, total, message)
    """

    dry_run: bool = Field(
        default=False,
        description="Validate without actually importing",
    )
    conflict_resolution: ConflictResolution = Field(
        default=ConflictResolution.SKIP,
        description="How to handle an existing (documentId, locale)",
    )
    import_media: bool = Field(
        default=True,
        description="Whether to import media files",
    )
    overwrite_media: bool = Field(
        default=False,
        description="Overwrite existing media files",
    )
    content_types: list[str] | None = Field(
        default=None,
        description="Specific content types to import (None = all)",
    )
    skip_relations: bool = Field(
        default=False,
        description="Skip importing relations (for initial pass)",
    )
    validate_relations: bool = Field(
        default=True,
        description="Validate relation targets exist",
    )
    batch_size: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Batch size for bulk operations",
    )
    progress_callback: Callable[[int, int, str], None] | None = Field(
        default=None,
        description="Optional progress callback(current, total, message)",
    )

    model_config = {"arbitrary_types_allowed": True}


class ImportResult(BaseModel):
    """Result of an import operation.

    Attributes:
        success: Whether import succeeded
        dry_run: Whether this was a dry run
        entities_imported: Number of entities imported
        entities_skipped: Number of entities skipped
        entities_updated: Number of entities updated
        entities_failed: Number of entities that failed
        relations_imported: Number of relation updates performed
        entities_to_publish: Live source rows that would be (or were) published
        media_imported: Number of media files imported
        media_skipped: Number of media files skipped
        errors: List of error messages
        warnings: List of warning messages
        id_mapping: Old numeric IDs to dest numeric IDs. Dry-run only
            includes dests that already exist; missing dests are counted,
            not mapped.
        doc_id_mapping: Old numeric IDs to dest documentIds. Dry-run does
            not record a source documentId as dest.
        doc_id_to_new_id: Source documentIds to dest numeric IDs. Same
            dry-run rule as id_mapping.
        doc_id_to_new_document_id: Source documentIds to dest documentIds.
            Same dry-run rule as doc_id_mapping.
    """

    success: bool = Field(..., description="Whether import succeeded")
    dry_run: bool = Field(..., description="Whether this was a dry run")
    entities_imported: int = Field(default=0, description="Entities imported")
    entities_skipped: int = Field(default=0, description="Entities skipped")
    entities_updated: int = Field(default=0, description="Entities updated")
    entities_failed: int = Field(default=0, description="Entities failed")
    relations_imported: int = Field(default=0, description="Relation updates performed")
    entities_to_publish: int = Field(
        default=0,
        description=(
            "Live source rows that would be published after relations. "
            "Dry-run counts intent without calling publish."
        ),
    )
    media_imported: int = Field(default=0, description="Media files imported")
    media_skipped: int = Field(default=0, description="Media files skipped")
    errors: list[str] = Field(default_factory=list, description="Error messages")
    warnings: list[str] = Field(default_factory=list, description="Warning messages")
    id_mapping: dict[str, dict[int, int]] = Field(
        default_factory=dict,
        description=(
            "Mapping of old IDs to dest IDs per content type. Dry-run only "
            "includes dests that already exist; missing dests are counted "
            "but not mapped as write targets."
        ),
    )
    doc_id_mapping: dict[str, dict[int, str]] = Field(
        default_factory=dict,
        description=(
            "Mapping of old IDs to dest documentIds per content type. "
            "Dry-run does not record a source documentId as dest."
        ),
    )
    doc_id_to_new_id: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description=(
            "Mapping of source documentIds to dest IDs. Dry-run only "
            "includes dests that already exist; missing dests are not "
            "mapped as write targets."
        ),
    )
    doc_id_to_new_document_id: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description=(
            "Mapping of source documentIds to dest documentIds. "
            "Dry-run does not record a source documentId as dest."
        ),
    )

    def add_error(self, error: str) -> None:
        """Add an error message.

        Args:
            error: Error message to add
        """
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add a warning message.

        Args:
            warning: Warning message to add
        """
        self.warnings.append(warning)

    def get_total_processed(self) -> int:
        """Get total number of entities processed.

        Returns:
            Sum of imported, skipped, updated, and failed
        """
        return (
            self.entities_imported
            + self.entities_skipped
            + self.entities_updated
            + self.entities_failed
        )
