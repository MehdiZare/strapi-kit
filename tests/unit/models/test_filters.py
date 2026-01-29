"""Tests for filter builder functionality."""

import pytest

from py_strapi.models.enums import FilterOperator
from py_strapi.models.request.filters import FilterBuilder, FilterCondition, FilterGroup


class TestFilterCondition:
    """Tests for FilterCondition model."""

    def test_simple_condition(self) -> None:
        """Test simple field-operator-value condition."""
        condition = FilterCondition(field="status", operator=FilterOperator.EQ, value="published")
        result = condition.to_dict()

        assert result == {"status": {"$eq": "published"}}

    def test_nested_field_condition(self) -> None:
        """Test condition with nested field (dot notation)."""
        condition = FilterCondition(field="author.name", operator=FilterOperator.EQ, value="John")
        result = condition.to_dict()

        assert result == {"author": {"name": {"$eq": "John"}}}

    def test_deeply_nested_field(self) -> None:
        """Test condition with deeply nested field."""
        condition = FilterCondition(
            field="post.author.profile.name", operator=FilterOperator.CONTAINS, value="Doe"
        )
        result = condition.to_dict()

        assert result == {"post": {"author": {"profile": {"name": {"$contains": "Doe"}}}}}

    def test_array_value(self) -> None:
        """Test condition with array value (IN operator)."""
        condition = FilterCondition(
            field="status", operator=FilterOperator.IN, value=["published", "draft"]
        )
        result = condition.to_dict()

        assert result == {"status": {"$in": ["published", "draft"]}}


class TestFilterGroup:
    """Tests for FilterGroup model."""

    def test_empty_group(self) -> None:
        """Test empty filter group returns empty dict."""
        group = FilterGroup()
        result = group.to_dict()

        assert result == {}

    def test_single_condition_no_operator(self) -> None:
        """Test group with single condition and no logical operator."""
        condition = FilterCondition(field="status", operator=FilterOperator.EQ, value="published")
        group = FilterGroup(conditions=[condition])
        result = group.to_dict()

        assert result == {"status": {"$eq": "published"}}

    def test_multiple_conditions_implicit_and(self) -> None:
        """Test group with multiple conditions (implicit AND)."""
        conditions = [
            FilterCondition(field="status", operator=FilterOperator.EQ, value="published"),
            FilterCondition(field="views", operator=FilterOperator.GT, value=100),
        ]
        group = FilterGroup(conditions=conditions)
        result = group.to_dict()

        # Should merge into single dict (implicit AND)
        assert result == {"status": {"$eq": "published"}, "views": {"$gt": 100}}

    def test_explicit_or_operator(self) -> None:
        """Test group with explicit OR operator."""
        conditions = [
            FilterCondition(field="views", operator=FilterOperator.GT, value=100),
            FilterCondition(field="likes", operator=FilterOperator.GT, value=50),
        ]
        group = FilterGroup(conditions=conditions, logical_operator=FilterOperator.OR)
        result = group.to_dict()

        assert result == {"$or": [{"views": {"$gt": 100}}, {"likes": {"$gt": 50}}]}

    def test_explicit_and_operator(self) -> None:
        """Test group with explicit AND operator."""
        conditions = [
            FilterCondition(field="status", operator=FilterOperator.EQ, value="published"),
            FilterCondition(field="views", operator=FilterOperator.GT, value=100),
        ]
        group = FilterGroup(conditions=conditions, logical_operator=FilterOperator.AND)
        result = group.to_dict()

        assert result == {
            "$and": [{"status": {"$eq": "published"}}, {"views": {"$gt": 100}}]
        }

    def test_not_operator(self) -> None:
        """Test group with NOT operator."""
        condition = FilterCondition(field="status", operator=FilterOperator.EQ, value="draft")
        group = FilterGroup(conditions=[condition], logical_operator=FilterOperator.NOT)
        result = group.to_dict()

        assert result == {"$not": [{"status": {"$eq": "draft"}}]}

    def test_nested_groups(self) -> None:
        """Test nested filter groups."""
        inner_group = FilterGroup(
            conditions=[
                FilterCondition(field="views", operator=FilterOperator.GT, value=100),
                FilterCondition(field="likes", operator=FilterOperator.GT, value=50),
            ],
            logical_operator=FilterOperator.OR,
        )

        outer_group = FilterGroup(
            conditions=[
                FilterCondition(field="status", operator=FilterOperator.EQ, value="published"),
                inner_group,
            ]
        )
        result = outer_group.to_dict()

        # Outer group has implicit AND, inner group has OR
        assert "status" in result
        assert "$or" in result
        assert result["status"] == {"$eq": "published"}
        assert result["$or"] == [{"views": {"$gt": 100}}, {"likes": {"$gt": 50}}]


class TestFilterBuilder:
    """Tests for FilterBuilder fluent API."""

    def test_empty_builder(self) -> None:
        """Test empty filter builder returns empty dict."""
        builder = FilterBuilder()
        result = builder.to_query_dict()

        assert result == {}

    def test_single_eq_filter(self) -> None:
        """Test builder with single equality filter."""
        builder = FilterBuilder().eq("status", "published")
        result = builder.to_query_dict()

        assert result == {"status": {"$eq": "published"}}

    def test_chained_filters_implicit_and(self) -> None:
        """Test chained filters (implicit AND)."""
        builder = (
            FilterBuilder().eq("status", "published").gt("views", 100).contains("title", "Python")
        )
        result = builder.to_query_dict()

        assert result == {
            "status": {"$eq": "published"},
            "views": {"$gt": 100},
            "title": {"$contains": "Python"},
        }

    # Equality operators
    def test_eq_operator(self) -> None:
        """Test equal operator."""
        builder = FilterBuilder().eq("status", "published")
        assert builder.to_query_dict() == {"status": {"$eq": "published"}}

    def test_eqi_operator(self) -> None:
        """Test case-insensitive equal operator."""
        builder = FilterBuilder().eqi("status", "PUBLISHED")
        assert builder.to_query_dict() == {"status": {"$eqi": "PUBLISHED"}}

    def test_ne_operator(self) -> None:
        """Test not equal operator."""
        builder = FilterBuilder().ne("status", "draft")
        assert builder.to_query_dict() == {"status": {"$ne": "draft"}}

    def test_nei_operator(self) -> None:
        """Test case-insensitive not equal operator."""
        builder = FilterBuilder().nei("status", "DRAFT")
        assert builder.to_query_dict() == {"status": {"$nei": "DRAFT"}}

    # Comparison operators
    def test_lt_operator(self) -> None:
        """Test less than operator."""
        builder = FilterBuilder().lt("price", 100)
        assert builder.to_query_dict() == {"price": {"$lt": 100}}

    def test_lte_operator(self) -> None:
        """Test less than or equal operator."""
        builder = FilterBuilder().lte("price", 100)
        assert builder.to_query_dict() == {"price": {"$lte": 100}}

    def test_gt_operator(self) -> None:
        """Test greater than operator."""
        builder = FilterBuilder().gt("views", 1000)
        assert builder.to_query_dict() == {"views": {"$gt": 1000}}

    def test_gte_operator(self) -> None:
        """Test greater than or equal operator."""
        builder = FilterBuilder().gte("views", 1000)
        assert builder.to_query_dict() == {"views": {"$gte": 1000}}

    # String matching operators
    def test_contains_operator(self) -> None:
        """Test contains operator."""
        builder = FilterBuilder().contains("title", "Python")
        assert builder.to_query_dict() == {"title": {"$contains": "Python"}}

    def test_not_contains_operator(self) -> None:
        """Test not contains operator."""
        builder = FilterBuilder().not_contains("title", "Java")
        assert builder.to_query_dict() == {"title": {"$notContains": "Java"}}

    def test_containsi_operator(self) -> None:
        """Test case-insensitive contains operator."""
        builder = FilterBuilder().containsi("title", "python")
        assert builder.to_query_dict() == {"title": {"$containsi": "python"}}

    def test_not_containsi_operator(self) -> None:
        """Test case-insensitive not contains operator."""
        builder = FilterBuilder().not_containsi("title", "java")
        assert builder.to_query_dict() == {"title": {"$notContainsi": "java"}}

    def test_starts_with_operator(self) -> None:
        """Test starts with operator."""
        builder = FilterBuilder().starts_with("title", "How to")
        assert builder.to_query_dict() == {"title": {"$startsWith": "How to"}}

    def test_starts_withi_operator(self) -> None:
        """Test case-insensitive starts with operator."""
        builder = FilterBuilder().starts_withi("title", "how to")
        assert builder.to_query_dict() == {"title": {"$startsWithi": "how to"}}

    def test_ends_with_operator(self) -> None:
        """Test ends with operator."""
        builder = FilterBuilder().ends_with("title", "Guide")
        assert builder.to_query_dict() == {"title": {"$endsWith": "Guide"}}

    def test_ends_withi_operator(self) -> None:
        """Test case-insensitive ends with operator."""
        builder = FilterBuilder().ends_withi("title", "guide")
        assert builder.to_query_dict() == {"title": {"$endsWithi": "guide"}}

    # Array operators
    def test_in_operator(self) -> None:
        """Test in array operator."""
        builder = FilterBuilder().in_("status", ["published", "draft"])
        assert builder.to_query_dict() == {"status": {"$in": ["published", "draft"]}}

    def test_not_in_operator(self) -> None:
        """Test not in array operator."""
        builder = FilterBuilder().not_in("status", ["archived", "deleted"])
        assert builder.to_query_dict() == {"status": {"$notIn": ["archived", "deleted"]}}

    # Null operators
    def test_null_operator_true(self) -> None:
        """Test null operator (is null)."""
        builder = FilterBuilder().null("deletedAt")
        assert builder.to_query_dict() == {"deletedAt": {"$null": True}}

    def test_null_operator_false(self) -> None:
        """Test null operator (is not null)."""
        builder = FilterBuilder().null("deletedAt", False)
        assert builder.to_query_dict() == {"deletedAt": {"$null": False}}

    def test_not_null_operator(self) -> None:
        """Test not null operator."""
        builder = FilterBuilder().not_null("publishedAt")
        assert builder.to_query_dict() == {"publishedAt": {"$notNull": True}}

    # Range operators
    def test_between_operator(self) -> None:
        """Test between operator."""
        builder = FilterBuilder().between("price", 10, 100)
        assert builder.to_query_dict() == {"price": {"$between": [10, 100]}}

    def test_between_operator_dates(self) -> None:
        """Test between operator with dates."""
        builder = FilterBuilder().between("publishedAt", "2024-01-01", "2024-12-31")
        assert builder.to_query_dict() == {
            "publishedAt": {"$between": ["2024-01-01", "2024-12-31"]}
        }

    # Logical operators
    def test_or_group(self) -> None:
        """Test OR group."""
        builder = FilterBuilder().or_group(
            FilterBuilder().eq("category", "tech"), FilterBuilder().eq("category", "science")
        )
        result = builder.to_query_dict()

        assert result == {"$or": [{"category": {"$eq": "tech"}}, {"category": {"$eq": "science"}}]}

    def test_and_group(self) -> None:
        """Test explicit AND group."""
        builder = FilterBuilder().and_group(
            FilterBuilder().eq("status", "published"), FilterBuilder().gt("views", 100)
        )
        result = builder.to_query_dict()

        assert result == {
            "$and": [{"status": {"$eq": "published"}}, {"views": {"$gt": 100}}]
        }

    def test_not_group(self) -> None:
        """Test NOT group."""
        builder = FilterBuilder().not_group(FilterBuilder().eq("status", "draft"))
        result = builder.to_query_dict()

        assert result == {"$not": [{"status": {"$eq": "draft"}}]}

    def test_complex_nested_logic(self) -> None:
        """Test complex nested logical operators."""
        # (status = published) AND (views > 1000 OR likes > 500)
        builder = FilterBuilder().eq("status", "published").or_group(
            FilterBuilder().gt("views", 1000), FilterBuilder().gt("likes", 500)
        )
        result = builder.to_query_dict()

        assert "status" in result
        assert "$or" in result
        assert result["status"] == {"$eq": "published"}
        assert result["$or"] == [{"views": {"$gt": 1000}}, {"likes": {"$gt": 500}}]

    def test_deep_relation_filter(self) -> None:
        """Test filtering on nested relation fields."""
        builder = FilterBuilder().eq("author.name", "John Doe")
        result = builder.to_query_dict()

        assert result == {"author": {"name": {"$eq": "John Doe"}}}

    def test_multiple_deep_relation_filters(self) -> None:
        """Test multiple filters on nested relations."""
        builder = (
            FilterBuilder()
            .eq("author.name", "John Doe")
            .eq("author.country", "USA")
            .gt("author.posts_count", 10)
        )
        result = builder.to_query_dict()

        assert result == {
            "author": {
                "name": {"$eq": "John Doe"},
                "country": {"$eq": "USA"},
                "posts_count": {"$gt": 10},
            }
        }
