"""Data seeding utilities for E2E tests.

This module provides utilities to seed test data into a Strapi instance
using the py-strapi client, which also serves as validation that the
package works correctly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from py_strapi.exceptions import StrapiError

if TYPE_CHECKING:
    from py_strapi import SyncClient
    from py_strapi.models.response.normalized import NormalizedEntity

logger = logging.getLogger(__name__)

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MEDIA_DIR = FIXTURES_DIR / "media"


@dataclass
class SeededEntity:
    """Represents a seeded entity with its ID and document_id."""

    id: int
    document_id: str | None
    data: dict


@dataclass
class SeededData:
    """Container for all seeded test data."""

    categories: list[SeededEntity] = field(default_factory=list)
    authors: list[SeededEntity] = field(default_factory=list)
    articles: list[SeededEntity] = field(default_factory=list)
    comments: list[SeededEntity] = field(default_factory=list)
    media: list[SeededEntity] = field(default_factory=list)

    def get_category_id(self, index: int = 0) -> int:
        """Get a category ID by index."""
        return self.categories[index].id

    def get_category_document_id(self, index: int = 0) -> str | None:
        """Get a category document_id by index."""
        return self.categories[index].document_id

    def get_author_id(self, index: int = 0) -> int:
        """Get an author ID by index."""
        return self.authors[index].id

    def get_author_document_id(self, index: int = 0) -> str | None:
        """Get an author document_id by index."""
        return self.authors[index].document_id

    def get_article_id(self, index: int = 0) -> int:
        """Get an article ID by index."""
        return self.articles[index].id

    def get_article_document_id(self, index: int = 0) -> str | None:
        """Get an article document_id by index."""
        return self.articles[index].document_id


def _entity_to_seeded(entity: NormalizedEntity, original_data: dict) -> SeededEntity:
    """Convert a NormalizedEntity to a SeededEntity."""
    return SeededEntity(
        id=entity.id,
        document_id=entity.document_id,
        data=original_data,
    )


class DataSeeder:
    """Seeds test data into a Strapi instance.

    This class creates test data using the py-strapi client,
    which validates that the package's create operations work correctly.

    Usage:
        seeder = DataSeeder(client)
        seeded = seeder.seed_all()

        # Use seeded data in tests
        article_id = seeded.get_article_id(0)

        # Clean up after tests
        seeder.cleanup(seeded)
    """

    def __init__(self, client: SyncClient) -> None:
        """Initialize the seeder with a Strapi client.

        Args:
            client: A configured SyncClient instance
        """
        self.client = client

    def seed_categories(self) -> list[SeededEntity]:
        """Seed category test data.

        Returns:
            List of created category entities

        Raises:
            RuntimeError: If category creation fails
        """
        categories_data = [
            {"name": "Technology", "slug": "technology", "description": "Tech articles"},
            {"name": "Science", "slug": "science", "description": "Science articles"},
            {"name": "Lifestyle", "slug": "lifestyle", "description": "Lifestyle articles"},
        ]

        seeded = []
        for data in categories_data:
            response = self.client.create("categories", data)
            if not response.data:
                raise RuntimeError(f"Failed to create category: {data!r}")
            seeded.append(_entity_to_seeded(response.data, data))

        return seeded

    def seed_authors(self) -> list[SeededEntity]:
        """Seed author test data.

        Returns:
            List of created author entities

        Raises:
            RuntimeError: If author creation fails
        """
        authors_data = [
            {
                "name": "John Doe",
                "email": "john.doe@example.com",
                "bio": "Senior tech writer with 10 years of experience.",
            },
            {
                "name": "Jane Smith",
                "email": "jane.smith@example.com",
                "bio": "Science journalist and researcher.",
            },
            {
                "name": "Bob Wilson",
                "email": "bob.wilson@example.com",
                "bio": "Lifestyle blogger and content creator.",
            },
        ]

        seeded = []
        for data in authors_data:
            response = self.client.create("authors", data)
            if not response.data:
                raise RuntimeError(f"Failed to create author: {data!r}")
            seeded.append(_entity_to_seeded(response.data, data))

        return seeded

    def seed_articles(
        self,
        authors: list[SeededEntity],
        categories: list[SeededEntity],
    ) -> list[SeededEntity]:
        """Seed article test data with relations.

        Args:
            authors: List of seeded authors (for relations)
            categories: List of seeded categories (for relations)

        Returns:
            List of created article entities

        Raises:
            ValueError: If insufficient authors or categories provided
            RuntimeError: If article creation fails
        """
        if len(authors) < 3:
            raise ValueError(f"seed_articles requires at least 3 authors, got {len(authors)}")
        if len(categories) < 3:
            raise ValueError(f"seed_articles requires at least 3 categories, got {len(categories)}")

        articles_data = [
            {
                "title": "Introduction to Python",
                "content": "Python is a versatile programming language...",
                "slug": "introduction-to-python",
                "status": "published",
                "views": 1500,
                "author": authors[0].document_id or authors[0].id,
                "category": categories[0].document_id or categories[0].id,
            },
            {
                "title": "The Future of AI",
                "content": "Artificial Intelligence is transforming industries...",
                "slug": "the-future-of-ai",
                "status": "published",
                "views": 2500,
                "author": authors[0].document_id or authors[0].id,
                "category": categories[0].document_id or categories[0].id,
            },
            {
                "title": "Climate Change Research",
                "content": "Recent studies show alarming trends...",
                "slug": "climate-change-research",
                "status": "published",
                "views": 800,
                "author": authors[1].document_id or authors[1].id,
                "category": categories[1].document_id or categories[1].id,
            },
            {
                "title": "Space Exploration Updates",
                "content": "NASA's latest missions reveal...",
                "slug": "space-exploration-updates",
                "status": "draft",
                "views": 0,
                "author": authors[1].document_id or authors[1].id,
                "category": categories[1].document_id or categories[1].id,
            },
            {
                "title": "Healthy Living Tips",
                "content": "Maintaining a healthy lifestyle...",
                "slug": "healthy-living-tips",
                "status": "published",
                "views": 3200,
                "author": authors[2].document_id or authors[2].id,
                "category": categories[2].document_id or categories[2].id,
            },
            {
                "title": "Travel Destinations 2024",
                "content": "Top travel spots to visit...",
                "slug": "travel-destinations-2024",
                "status": "archived",
                "views": 1200,
                "author": authors[2].document_id or authors[2].id,
                "category": categories[2].document_id or categories[2].id,
            },
        ]

        seeded = []
        for data in articles_data:
            response = self.client.create("articles", data)
            if not response.data:
                raise RuntimeError(f"Failed to create article: {data!r}")
            seeded.append(_entity_to_seeded(response.data, data))

        return seeded

    def seed_comments(self, articles: list[SeededEntity]) -> list[SeededEntity]:
        """Seed comment test data with relations.

        Args:
            articles: List of seeded articles (for relations)

        Returns:
            List of created comment entities

        Raises:
            ValueError: If insufficient articles provided
            RuntimeError: If comment creation fails
        """
        if len(articles) < 3:
            raise ValueError(f"seed_comments requires at least 3 articles, got {len(articles)}")

        comments_data = [
            {
                "content": "Great introduction! Very helpful for beginners.",
                "approved": True,
                "author_name": "Reader One",
                "article": articles[0].document_id or articles[0].id,
            },
            {
                "content": "I learned a lot from this article.",
                "approved": True,
                "author_name": "Reader Two",
                "article": articles[0].document_id or articles[0].id,
            },
            {
                "content": "Interesting perspective on AI.",
                "approved": True,
                "author_name": "Tech Fan",
                "article": articles[1].document_id or articles[1].id,
            },
            {
                "content": "This comment is pending review.",
                "approved": False,
                "author_name": "New User",
                "article": articles[1].document_id or articles[1].id,
            },
            {
                "content": "Important research findings!",
                "approved": True,
                "author_name": "Science Lover",
                "article": articles[2].document_id or articles[2].id,
            },
        ]

        seeded = []
        for data in comments_data:
            response = self.client.create("comments", data)
            if not response.data:
                raise RuntimeError(f"Failed to create comment: {data!r}")
            seeded.append(_entity_to_seeded(response.data, data))

        return seeded

    def seed_media(self) -> list[SeededEntity]:
        """Seed media files from fixtures directory.

        Returns:
            List of uploaded media entities
        """
        seeded = []

        # Check if test media files exist
        test_image = MEDIA_DIR / "test-image.jpg"
        if test_image.exists():
            media = self.client.upload_file(
                str(test_image),
                alternative_text="Test image for E2E tests",
                caption="A sample test image",
            )
            if media:
                seeded.append(
                    SeededEntity(
                        id=media.id,
                        document_id=getattr(media, "document_id", None),
                        data={"name": media.name, "url": media.url},
                    )
                )

        test_pdf = MEDIA_DIR / "test-document.pdf"
        if test_pdf.exists():
            media = self.client.upload_file(
                str(test_pdf),
                alternative_text="Test PDF for E2E tests",
                caption="A sample test document",
            )
            if media:
                seeded.append(
                    SeededEntity(
                        id=media.id,
                        document_id=getattr(media, "document_id", None),
                        data={"name": media.name, "url": media.url},
                    )
                )

        return seeded

    def seed_all(self, include_media: bool = False) -> SeededData:
        """Seed all test data in the correct order.

        Creates categories, authors, articles, and comments in
        dependency order (categories/authors first, then articles,
        then comments).

        Args:
            include_media: Whether to seed media files (default: False)

        Returns:
            SeededData containing all created entities
        """
        seeded = SeededData()

        # Seed in dependency order
        seeded.categories = self.seed_categories()
        seeded.authors = self.seed_authors()
        seeded.articles = self.seed_articles(seeded.authors, seeded.categories)
        seeded.comments = self.seed_comments(seeded.articles)

        if include_media:
            seeded.media = self.seed_media()

        return seeded

    def cleanup(self, seeded: SeededData) -> None:
        """Remove all seeded data in reverse dependency order.

        Args:
            seeded: The SeededData to clean up
        """
        # Delete in reverse dependency order
        for comment in reversed(seeded.comments):
            try:
                comment_id = comment.document_id or str(comment.id)
                self.client.remove(f"comments/{comment_id}")
            except StrapiError as exc:
                logger.warning("Failed to delete comment %s: %s", comment_id, exc)

        for article in reversed(seeded.articles):
            try:
                article_id = article.document_id or str(article.id)
                self.client.remove(f"articles/{article_id}")
            except StrapiError as exc:
                logger.warning("Failed to delete article %s: %s", article_id, exc)

        for author in reversed(seeded.authors):
            try:
                author_id = author.document_id or str(author.id)
                self.client.remove(f"authors/{author_id}")
            except StrapiError as exc:
                logger.warning("Failed to delete author %s: %s", author_id, exc)

        for category in reversed(seeded.categories):
            try:
                category_id = category.document_id or str(category.id)
                self.client.remove(f"categories/{category_id}")
            except StrapiError as exc:
                logger.warning("Failed to delete category %s: %s", category_id, exc)

        for media in reversed(seeded.media):
            try:
                self.client.delete_media(media.id)
            except StrapiError as exc:
                logger.warning("Failed to delete media %s: %s", media.id, exc)


# Convenience function for simple usage
def seed_test_data(client: SyncClient, include_media: bool = False) -> SeededData:
    """Convenience function to seed all test data.

    Args:
        client: A configured SyncClient
        include_media: Whether to include media files

    Returns:
        SeededData containing all created entities
    """
    seeder = DataSeeder(client)
    return seeder.seed_all(include_media=include_media)


def cleanup_test_data(client: SyncClient, seeded: SeededData) -> None:
    """Convenience function to clean up seeded data.

    Args:
        client: A configured SyncClient
        seeded: The SeededData to clean up
    """
    seeder = DataSeeder(client)
    seeder.cleanup(seeded)
