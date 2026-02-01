"""Models for bulk operation results.

This module provides models for tracking results of bulk operations
like bulk_create, bulk_update, and bulk_delete.
"""

from typing import Any

from pydantic import BaseModel, Field

from .response.normalized import NormalizedEntity


class BulkOperationFailure(BaseModel):
    """Represents a failed item in a bulk operation.

    Attributes:
        index: Position in original list
        item: Original item data
        error: Error message
        exception: Original exception (if available)
    """

    index: int = Field(..., description="Index in original list")
    item: dict[str, Any] = Field(..., description="Original item data")
    error: str = Field(..., description="Error message")
    exception: Exception | None = Field(None, description="Original exception")

    model_config = {"arbitrary_types_allowed": True}


class BulkOperationResult(BaseModel):
    """Result of a bulk operation.

    Attributes:
        successes: Successfully processed entities
        failures: Failed items with error details
        total: Total items attempted
        succeeded: Count of successful items
        failed: Count of failed items
    """

    successes: list[NormalizedEntity] = Field(
        default_factory=list, description="Successfully processed entities"
    )
    failures: list[BulkOperationFailure] = Field(
        default_factory=list, description="Failed items with errors"
    )
    total: int = Field(..., description="Total items")
    succeeded: int = Field(..., description="Successful count")
    failed: int = Field(..., description="Failed count")

    def is_complete_success(self) -> bool:
        """Check if all items succeeded.

        Returns:
            True if all items succeeded, False otherwise
        """
        return self.failed == 0

    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0).

        Returns:
            Success rate as a float between 0.0 and 1.0
        """
        if self.total == 0:
            return 0.0
        return self.succeeded / self.total
