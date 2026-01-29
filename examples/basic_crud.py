"""Basic CRUD operations example.

This example demonstrates how to perform basic CRUD operations
using the synchronous client.
"""

from py_strapi import StrapiConfig, SyncClient


def main() -> None:
    """Demonstrate basic CRUD operations."""
    # Configure client
    config = StrapiConfig(
        base_url="http://localhost:1337",
        api_token="your-api-token-here",
    )

    # Use client with context manager for automatic cleanup
    with SyncClient(config) as client:
        print("Connected to Strapi")
        print(f"API Version: {client.api_version or 'auto-detecting...'}")

        # GET request - List articles
        print("\n1. Listing articles...")
        try:
            response = client.get("articles", params={"pagination[limit]": 5})
            print(f"Found {len(response.get('data', []))} articles")
        except Exception as e:
            print(f"Error: {e}")

        # POST request - Create article
        print("\n2. Creating new article...")
        try:
            new_article = {
                "data": {
                    "title": "Test Article from strapi-kit",
                    "content": "This article was created using the strapi-kit library.",
                }
            }
            response = client.post("articles", json=new_article)
            article_id = response.get("data", {}).get("id")
            print(f"Created article with ID: {article_id}")
        except Exception as e:
            print(f"Error: {e}")

        # PUT request - Update article
        print("\n3. Updating article...")
        try:
            if article_id:
                update_data = {
                    "data": {
                        "title": "Updated Article Title",
                    }
                }
                response = client.put(f"articles/{article_id}", json=update_data)
                print(f"Updated article: {response.get('data', {}).get('title')}")
        except Exception as e:
            print(f"Error: {e}")

        # GET request - Get single article
        print("\n4. Getting single article...")
        try:
            if article_id:
                response = client.get(f"articles/{article_id}")
                print(f"Retrieved: {response.get('data', {}).get('title')}")
        except Exception as e:
            print(f"Error: {e}")

        # DELETE request - Delete article
        print("\n5. Deleting article...")
        try:
            if article_id:
                response = client.delete(f"articles/{article_id}")
                print("Article deleted successfully")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
